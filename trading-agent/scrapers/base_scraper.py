try:
    from DrissionPage import ChromiumPage, ChromiumOptions  # type: ignore[import-untyped, import-not-found]
except ImportError:
    ChromiumPage = None  # type: ignore[assignment, misc]
    ChromiumOptions = None  # type: ignore[assignment, misc]

import logging
import time
import uuid
import tempfile
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger("TradingAgent.Scraper")


def kill_process_tree(pid: Optional[int]) -> bool:
    """
    Terminates a process and all its children/descendants.
    Uses psutil if available, with a fallback to Windows taskkill /F /T /PID or POSIX SIGKILL.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False

    killed = False
    # 1. Try psutil
    try:
        import psutil
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            parent.kill()
            psutil.wait_procs(children + [parent], timeout=2)
            killed = True
        except psutil.NoSuchProcess:
            killed = True
        except Exception as p_err:
            logger.debug(f"psutil process tree kill failed for PID {pid}: {p_err}")
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"psutil unexpected error for PID {pid}: {e}")

    # 2. Fallback for Windows or if psutil was not installed / failed
    if not killed:
        import platform
        import subprocess
        try:
            if platform.system().lower() == "windows":
                cmd = ["taskkill", "/F", "/T", "/PID", str(pid)]
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                killed = True
            else:
                import os
                import signal
                sig = getattr(signal, "SIGKILL", getattr(signal, "SIGTERM", 9))
                os.kill(pid, sig)
                killed = True
        except Exception as e:
            logger.debug(f"Fallback process tree kill failed for PID {pid}: {e}")

    return killed


class BaseScraper:
    def __init__(self, headless=True, profile_name=None):
        self.headless = headless
        self.profile_name = profile_name
        self._temp_profile_dir = None
        self.is_closed = False
        self.browser_pid: Optional[int] = None
        self.page = self._initialize_browser(self.headless)
        
    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _detect_browser_path(self) -> str | None:
        import os
        candidate_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for path in candidate_paths:
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def _cleanup_stale_profile_locks(profile_dir: Path) -> None:
        """Membersihkan file lock sisa crash agar sesi browser berikutnya tidak gagal start."""
        if not profile_dir.exists():
            return
        lock_names = ["LOCK", "SingletonLock", "SingletonSocket", "SingletonCookie"]
        for target_dir in [profile_dir, profile_dir / "Default"]:
            if target_dir.exists():
                for name in lock_names:
                    try:
                        p = target_dir / name
                        if p.exists():
                            p.unlink(missing_ok=True)
                    except Exception:
                        pass

    def _initialize_browser(self, headless: bool, port: int = 0):
        if ChromiumOptions is None or ChromiumPage is None:
            logger.warning("DrissionPage is not installed. Browser automation unavailable.")
            return None
        import socket
        options = ChromiumOptions()
        
        if port == 0:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            sock.close()
            
        options.set_local_port(port)

        # Gunakan binary browser native (Edge/Chrome) jika terpasang untuk fingerprint TLS asli
        browser_bin = self._detect_browser_path()
        if browser_bin:
            options.set_browser_path(browser_bin)
        
        if self.profile_name:
            import os
            base_dir = Path(os.getcwd())
            profile_dir = base_dir / "data" / "sessions" / "browser_profile" / self.profile_name
            profile_dir.mkdir(parents=True, exist_ok=True)
            self._cleanup_stale_profile_locks(profile_dir)
            options.set_user_data_path(str(profile_dir))
        else:
            # Profil sementara untuk menghindari cache kotor
            session_id = uuid.uuid4().hex[:8]
            profile_dir = Path(tempfile.gettempdir()) / f"trading_agent_browser_{session_id}"
            options.set_user_data_path(str(profile_dir))
            self._temp_profile_dir = profile_dir
        
        # DNS over HTTPS untuk melewati pemblokiran level ISP/DNS
        options.set_pref("dns_over_https.mode", "secure")
        options.set_pref("dns_over_https.templates", "https://cloudflare-dns.com/dns-query")
        
        options.set_timeouts(base=20, page_load=25, script=15)
        
        options.headless(headless)
        
        # User-agent desktop realistis untuk menghindari deteksi HeadlessChrome bot
        options.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        
        # Strategi anti-deteksi dan peningkatan performa
        options.set_argument('--no-sandbox')
        options.set_argument('--disable-gpu')
        options.set_argument('--disable-dev-shm-usage')
        options.set_argument('--disable-blink-features=AutomationControlled')
        options.set_argument('--disable-extensions')

        # Penegakan locale English dan nonaktifkan fitur terjemahan otomatis browser
        options.set_argument('--lang=en-US,en')
        options.set_argument('--disable-features=Translate')
        options.set_argument('--disable-translate')
        options.set_pref('intl.accept_languages', 'en-US,en')
        options.set_pref('translate.enabled', False)
        options.set_pref('translate_whitelists', {})

        page = None
        try:
            page = ChromiumPage(options)
        except Exception as init_err:
            logger.warning(f"Failed to initialize ChromiumPage on port {port} (profile: {self.profile_name}): {init_err}")
            # Fallback otomatis ke profil sementara bersih jika direktori profil bermasalah/terkunci
            session_id = uuid.uuid4().hex[:8]
            fallback_dir = Path(tempfile.gettempdir()) / f"trading_agent_browser_fb_{session_id}"
            self._temp_profile_dir = fallback_dir
            options.set_user_data_path(str(fallback_dir))
            import random
            fallback_port = random.randint(18000, 25000)
            options.set_local_port(fallback_port)
            try:
                page = ChromiumPage(options)
                logger.info(f"ChromiumPage successfully recovered using ephemeral profile on port {fallback_port}")
            except Exception as fb_err:
                logger.error(f"Fallback ChromiumPage initialization also failed: {fb_err}")
                return None

        try:
            self.browser_pid = getattr(page, "process_id", None)
            if self.browser_pid is None and hasattr(page, "browser"):
                self.browser_pid = getattr(page.browser, "process_id", None)
            if self.browser_pid is None and hasattr(page, "_browser"):
                self.browser_pid = getattr(page._browser, "process_id", None)
            if self.browser_pid is None and hasattr(page, "_process_id"):
                self.browser_pid = getattr(page, "_process_id", None)
        except Exception:
            self.browser_pid = None
        return page

    def _is_cloudflare_challenge(self) -> bool:
        """Mendeteksi apakah halaman sedang menampilkan Cloudflare challenge / Turnstile."""
        if not self.page:
            return False
        try:
            page_obj: Any = self.page
            title = page_obj.title.lower() if hasattr(page_obj, "title") and page_obj.title else ""
            cf_phrases = [
                "just a moment",
                "tunggu sebentar",
                "attention required",
                "security check",
                "pemeriksaan keamanan",
                "memeriksa koneksi",
                "verifikasi",
                "checking your browser",
                "cloudflare",
            ]
            if any(phrase in title for phrase in cf_phrases):
                return True
            if page_obj.ele("css:#challenge-running, #challenge-stage, div.cf-turnstile, #turnstile-wrapper, #cf-wrapper", timeout=0.5):
                return True
            if page_obj.ele('xpath://iframe[contains(@src, "challenges.cloudflare.com") or contains(@src, "turnstile")]', timeout=0.5):
                return True
        except Exception:
            pass
        return False

    def _handle_cloudflare_challenge(self, wait_selector: Optional[str] = None, timeout: int = 40) -> bool:
        """Menangani atau menunggu penyelesaian Cloudflare challenge / Turnstile."""
        if not self.page:
            return False
        logger.info(f"Cloudflare verification detected. Waiting up to {timeout}s for challenge pass...")
        end_time = time.time() + timeout
        page_obj: Any = self.page
        
        while time.time() < end_time:
            if getattr(self, 'is_closed', False):
                return False
            try:
                cf_iframe = page_obj.get_frame('xpath://iframe[contains(@src, "challenges.cloudflare.com") or contains(@src, "turnstile")]')
                if cf_iframe:
                    cb = cf_iframe.ele('xpath://input[@type="checkbox"] | //span[contains(@class, "mark")] | //div[contains(@class, "cb-lb")]', timeout=1)
                    if cb:
                        logger.info("Attempting auto-click on Cloudflare Turnstile checkbox...")
                        cb.click()
            except Exception:
                pass

            try:
                direct_cb = page_obj.ele('css:div.cf-turnstile input[type="checkbox"], #turnstile-wrapper input[type="checkbox"]', timeout=0.5)
                if direct_cb:
                    logger.info("Attempting auto-click on direct Turnstile checkbox...")
                    direct_cb.click()
            except Exception:
                pass
            
            if wait_selector:
                try:
                    if page_obj.wait.ele_displayed(wait_selector, timeout=2):
                        logger.info(f"Challenge resolved! Target selector {wait_selector} is displayed.")
                        return True
                except Exception:
                    pass
            elif not self._is_cloudflare_challenge():
                logger.info("Cloudflare challenge cleared.")
                return True

            time.sleep(1.5)
            
        return False

    def _prepare_session(self):
        """Hook yang dapat di-override subclass untuk injeksi cookie/auth sebelum navigasi."""
        pass

    def navigate_with_fallback(self, url: str, wait_selector: Optional[str] = None, disable_fallback: bool = False, timeout: int = 30) -> bool:
        """
        Mencoba navigasi ke URL. Jika terdeteksi Cloudflare challenge atau pemblokiran,
        sistem akan menangani challenge atau beralih ke mode non-headless sebagai cadangan.
        """
        if getattr(self, 'is_closed', False):
            return False
        if not self.page:
            return False if disable_fallback else self._fallback(url, wait_selector)
        try:
            page_obj: Any = self.page
            self._prepare_session()
            logger.info(f"Navigating to {url} (Headless: {self.headless})")
            page_obj.get(url)

            if wait_selector:
                if page_obj.wait.ele_displayed(wait_selector, timeout=timeout):
                    return True
                
                # Jika selector belum muncul, periksa apakah ada Cloudflare challenge
                if self._is_cloudflare_challenge():
                    if self._handle_cloudflare_challenge(wait_selector=wait_selector, timeout=15):
                        return True
                    if self.headless:
                        logger.info("Cloudflare challenge detected in headless mode and unresolved. Switching to non-headless fallback...")
                        return False if disable_fallback else self._fallback(url, wait_selector)

                logger.warning(f"Selector {wait_selector} not found. Possible block or slow loading.")
                return False if disable_fallback else self._fallback(url, wait_selector)
            
            return True
            
        except Exception as e:
            logger.warning(f"Navigation failed: {e}")
            return False if disable_fallback else self._fallback(url, wait_selector)

    def _fallback(self, url: str, wait_selector: Optional[str] = None) -> bool:
        if getattr(self, 'is_closed', False):
            return False
        if not self.headless:
            logger.error("Already in non-headless mode and failed. Aborting.")
            return False
            
        import os
        allow_gui = os.getenv("SCRAPER_ALLOW_GUI_FALLBACK", "false").lower() in ("true", "1", "yes")
        if not allow_gui:
            if self._is_cloudflare_challenge():
                logger.warning("[BaseScraper] Cloudflare challenge encountered in headless mode. GUI fallback disabled (set SCRAPER_ALLOW_GUI_FALLBACK=true to enable). Aborting.")
            else:
                logger.warning(f"[BaseScraper] Selector {wait_selector} not resolved in headless mode. GUI fallback disabled. Aborting.")
            return False

        logger.info("Falling back to non-headless mode...")
        self.close()
        self.is_closed = False
        self.headless = False
        import random
        new_port = random.randint(9300, 9500)
        self.page = self._initialize_browser(False, port=new_port)
        if not self.page:
            return False
        page_obj: Any = self.page
        
        try:
            self._prepare_session()
            page_obj.get(url)
            if self._is_cloudflare_challenge():
                if self._handle_cloudflare_challenge(wait_selector=wait_selector, timeout=45):
                    return True

            if wait_selector:
                logger.info(f"Waiting up to 45 seconds for {wait_selector}. Solve CAPTCHA if it appears.")
                return page_obj.wait.ele_displayed(wait_selector, timeout=45)
            return True
        except Exception as e:
            logger.error(f"Fallback navigation also failed: {e}")
            return False

    def close(self):
        self.is_closed = True
        pid = getattr(self, 'browser_pid', None)
        if pid is None and hasattr(self, 'page') and self.page:
            try:
                pid = getattr(self.page, "process_id", None)
                if pid is None and hasattr(self.page, "browser"):
                    pid = getattr(self.page.browser, "process_id", None)
                if pid is None and hasattr(self.page, "_browser"):
                    pid = getattr(self.page._browser, "process_id", None)
            except Exception:
                pass

        try:
            if hasattr(self, 'page') and self.page:
                try:
                    self.page.quit(timeout=2, force=True)
                except TypeError:
                    self.page.quit()
        except Exception as e:
            logger.debug(f"Error during page.quit(): {e}")
        finally:
            if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                kill_process_tree(pid)
                self.browser_pid = None
            self._cleanup_temp_dir()

    def _cleanup_temp_dir(self):
        if hasattr(self, '_temp_profile_dir') and self._temp_profile_dir:
            import shutil
            try:
                shutil.rmtree(self._temp_profile_dir, ignore_errors=True)
            except Exception:
                pass
