# ==============================================================================
# File: analysis/mcp/servers/google_sheets_server.py
# Description: Built-in Google Sheets and Google Docs MCP Server
# Provides read/write access to Google Spreadsheets and Docs via Service Account.
# ==============================================================================

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request

from analysis.mcp.protocol import (
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    LATEST_PROTOCOL_VERSION,
    make_error_response,
    make_result_response,
)


class GoogleSheetsMcpServer:
    """Stdio-based MCP Server for Google Sheets and Google Docs."""

    def __init__(self, creds_path: Optional[str] = None):
        self.name = "google-sheets-server"
        self.version = "1.0.0"
        
        self.creds_path = creds_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "config/google_credentials.json"
        if not os.path.isabs(self.creds_path):
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.creds_path = str(base_dir / self.creds_path)
            
        self.default_folder_id = os.environ.get("GOOGLE_DRIVE_FOLDER_ID", "15PKGN6q0UUab-2dc8AcAXMTG8L5jMRnd")
        self.user_email = os.environ.get("GOOGLE_USER_EMAIL", "asaifulakbarw@gmail.com")
        self.scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/presentations",
        ]
        self._gc: Optional[gspread.Client] = None
        self._creds: Optional[Credentials] = None

    def _get_credentials(self) -> Credentials:
        if not os.path.exists(self.creds_path):
            raise FileNotFoundError(f"Google credentials file not found: {self.creds_path}")
        if self._creds is None or (hasattr(self._creds, "expired") and self._creds.expired):
            self._creds = Credentials.from_service_account_file(self.creds_path, scopes=self.scopes)
        return self._creds

    def _get_gspread_client(self) -> gspread.Client:
        if self._gc is None:
            creds = self._get_credentials()
            self._gc = gspread.authorize(creds)
        return self._gc

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "gsheets_list_files",
                "description": "List files (Google Sheets and Google Docs) inside a Google Drive folder.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "folder_id": {
                            "type": "string",
                            "description": "Optional Google Drive Folder ID. Defaults to configured workspace folder.",
                        }
                    },
                },
            },
            {
                "name": "gsheets_read_sheet",
                "description": "Read all rows from a Google Sheet worksheet as structured JSON records.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "spreadsheet_id_or_name": {
                            "type": "string",
                            "description": "Google Spreadsheet ID or exact title name.",
                        },
                        "worksheet_name": {
                            "type": "string",
                            "description": "Name of the worksheet tab. Defaults to the first tab.",
                        },
                        "max_rows": {
                            "type": "integer",
                            "description": "Maximum number of rows to return (default: 100).",
                        },
                    },
                    "required": ["spreadsheet_id_or_name"],
                },
            },
            {
                "name": "gsheets_append_row",
                "description": "Append a data row (as dictionary or list) to a Google Sheet.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "spreadsheet_id_or_name": {
                            "type": "string",
                            "description": "Google Spreadsheet ID or exact title name.",
                        },
                        "row_data": {
                            "type": "object",
                            "description": "Row data key-value dictionary (e.g. {'Date': '2026-09-30', 'Symbol': 'XAUUSD', 'Action': 'BUY', 'Lots': 0.10, 'Status': 'FILLED'}).",
                        },
                        "worksheet_name": {
                            "type": "string",
                            "description": "Name of the worksheet tab. Defaults to the first tab.",
                        },
                    },
                    "required": ["spreadsheet_id_or_name", "row_data"],
                },
            },
            {
                "name": "gsheets_create_worksheet",
                "description": "Create a new tab / worksheet in an existing Google Spreadsheet (e.g. for a new month).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "spreadsheet_id_or_name": {
                            "type": "string",
                            "description": "Google Spreadsheet ID or exact title name.",
                        },
                        "title": {
                            "type": "string",
                            "description": "Name for the new worksheet tab (e.g. '2026-10' or 'October').",
                        },
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of column header strings to initialize the first row.",
                        },
                    },
                    "required": ["spreadsheet_id_or_name", "title"],
                },
            },
            {
                "name": "gdocs_read_doc",
                "description": "Read text content from a Google Document.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "Google Document ID (from URL).",
                        }
                    },
                    "required": ["document_id"],
                },
            },
            {
                "name": "gdocs_append_text",
                "description": "Append text content to an existing Google Document.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "Google Document ID (from URL).",
                        },
                        "text": {
                            "type": "string",
                            "description": "Text to append to the document.",
                        },
                    },
                    "required": ["document_id", "text"],
                },
            },
            {
                "name": "gslides_read_presentation",
                "description": "Read slide texts and structure of a Google Slides presentation.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "presentation_id": {
                            "type": "string",
                            "description": "Google Slides Presentation ID (from URL).",
                        }
                    },
                    "required": ["presentation_id"],
                },
            },
            {
                "name": "gslides_append_slide",
                "description": "Create a new slide in a Google Slides presentation with a title and body text.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "presentation_id": {
                            "type": "string",
                            "description": "Google Slides Presentation ID (from URL).",
                        },
                        "title": {
                            "type": "string",
                            "description": "Title of the slide.",
                        },
                        "body_text": {
                            "type": "string",
                            "description": "Body text of the slide.",
                        },
                    },
                    "required": ["presentation_id", "title", "body_text"],
                },
            },
        ]

    def _open_spreadsheet(self, gc: gspread.Client, identifier: str) -> gspread.Spreadsheet:
        if len(identifier) > 30 and ("/" not in identifier and " " not in identifier):
            return gc.open_by_key(identifier)
        try:
            return gc.open_by_key(identifier)
        except Exception:
            return gc.open(identifier)

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any]) -> Any:
        gc = self._get_gspread_client()

        if tool_name == "gsheets_list_files":
            creds = self._get_credentials()
            creds.refresh(Request())
            folder_id = args.get("folder_id") or self.default_folder_id
            
            url = "https://www.googleapis.com/drive/v3/files"
            params = {
                "q": f"'{folder_id}' in parents and trashed=false",
                "fields": "files(id, name, mimeType, webViewLink, modifiedTime)",
                "pageSize": 50,
            }
            resp = requests.get(url, headers={"Authorization": f"Bearer {creds.token}"}, params=params)
            if resp.status_code != 200:
                raise RuntimeError(f"Drive API error: {resp.text}")
            files = resp.json().get("files", [])
            return {"folder_id": folder_id, "count": len(files), "files": files}

        elif tool_name == "gsheets_read_sheet":
            s_id = args.get("spreadsheet_id_or_name")
            if not s_id:
                raise ValueError("Missing 'spreadsheet_id_or_name'")
            sh = self._open_spreadsheet(gc, s_id)
            w_name = args.get("worksheet_name")
            ws = sh.worksheet(w_name) if w_name else sh.sheet1
            
            records = ws.get_all_records()
            max_rows = args.get("max_rows", 100)
            return {
                "spreadsheet_title": sh.title,
                "spreadsheet_id": sh.id,
                "worksheet": ws.title,
                "total_rows": len(records),
                "records": records[:max_rows],
            }

        elif tool_name == "gsheets_append_row":
            s_id = args.get("spreadsheet_id_or_name")
            row_data = args.get("row_data")
            if not s_id or row_data is None:
                raise ValueError("Missing 'spreadsheet_id_or_name' or 'row_data'")
            sh = self._open_spreadsheet(gc, s_id)
            w_name = args.get("worksheet_name")
            ws = sh.worksheet(w_name) if w_name else sh.sheet1

            if isinstance(row_data, dict):
                existing_headers = ws.row_values(1)
                if not existing_headers:
                    headers = list(row_data.keys())
                    values = list(row_data.values())
                    ws.append_row(headers)
                    ws.append_row(values)
                    return {"status": "initialized_and_appended", "headers": headers, "values": values}
                else:
                    aligned_row = [row_data.get(h, "") for h in existing_headers]
                    ws.append_row(aligned_row)
                    return {"status": "appended", "row": aligned_row}
            elif isinstance(row_data, list):
                ws.append_row(row_data)
                return {"status": "appended", "row": row_data}
            else:
                raise ValueError("row_data must be a dict or list")

        elif tool_name == "gsheets_create_worksheet":
            s_id = args.get("spreadsheet_id_or_name")
            title = args.get("title")
            if not s_id or not title:
                raise ValueError("Missing 'spreadsheet_id_or_name' or 'title'")
            sh = self._open_spreadsheet(gc, s_id)
            ws = sh.add_worksheet(title=title, rows=100, cols=20)
            headers = args.get("headers")
            if headers and isinstance(headers, list):
                ws.append_row(headers)
            return {"status": "worksheet_created", "worksheet": title, "spreadsheet_id": sh.id}

        elif tool_name == "gdocs_read_doc":
            doc_id = args.get("document_id")
            if not doc_id:
                raise ValueError("Missing 'document_id'")
            creds = self._get_credentials()
            creds.refresh(Request())
            url = f"https://docs.googleapis.com/v1/documents/{doc_id}"
            resp = requests.get(url, headers={"Authorization": f"Bearer {creds.token}"})
            if resp.status_code != 200:
                raise RuntimeError(f"Docs API error: {resp.text}")
            doc_data = resp.json()
            title = doc_data.get("title", "")
            body = doc_data.get("body", {}).get("content", [])
            text_chunks = []
            for element in body:
                paragraph = element.get("paragraph")
                if paragraph:
                    for part in paragraph.get("elements", []):
                        text_run = part.get("textRun")
                        if text_run and "content" in text_run:
                            text_chunks.append(text_run["content"])
            full_text = "".join(text_chunks)
            return {"document_id": doc_id, "title": title, "content": full_text}

        elif tool_name == "gdocs_append_text":
            doc_id = args.get("document_id")
            text = args.get("text")
            if not doc_id or text is None:
                raise ValueError("Missing 'document_id' or 'text'")
            creds = self._get_credentials()
            creds.refresh(Request())
            
            # Fetch doc length first
            get_url = f"https://docs.googleapis.com/v1/documents/{doc_id}"
            r_get = requests.get(get_url, headers={"Authorization": f"Bearer {creds.token}"})
            if r_get.status_code != 200:
                raise RuntimeError(f"Docs API error: {r_get.text}")
            doc = r_get.json()
            body_content = doc.get("body", {}).get("content", [])
            end_index = body_content[-1].get("endIndex", 1) - 1 if body_content else 1
            if end_index < 1:
                end_index = 1

            batch_url = f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate"
            requests_body = {
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": end_index},
                            "text": f"\n{text}\n",
                        }
                    }
                ]
            }
            resp = requests.post(batch_url, headers={"Authorization": f"Bearer {creds.token}"}, json=requests_body)
            if resp.status_code != 200:
                raise RuntimeError(f"Docs API insert error: {resp.text}")
            return {"status": "appended", "document_id": doc_id}

        elif tool_name == "gslides_read_presentation":
            p_id = args.get("presentation_id")
            if not p_id:
                raise ValueError("Missing 'presentation_id'")
            creds = self._get_credentials()
            creds.refresh(Request())
            url = f"https://slides.googleapis.com/v1/presentations/{p_id}"
            resp = requests.get(url, headers={"Authorization": f"Bearer {creds.token}"})
            if resp.status_code != 200:
                raise RuntimeError(f"Slides API error: {resp.text}")
            data = resp.json()
            title = data.get("title", "")
            slides = data.get("slides", [])
            slide_summaries = []
            for idx, s in enumerate(slides, start=1):
                texts = []
                for pe in s.get("pageElements", []):
                    shape = pe.get("shape", {})
                    text_data = shape.get("text", {})
                    for te in text_data.get("textElements", []):
                        auto_text = te.get("textRun", {}).get("content", "")
                        if auto_text.strip():
                            texts.append(auto_text.strip())
                slide_summaries.append({
                    "slide_number": idx,
                    "slide_id": s.get("objectId"),
                    "texts": texts,
                })
            return {"presentation_id": p_id, "title": title, "slide_count": len(slides), "slides": slide_summaries}

        elif tool_name == "gslides_append_slide":
            p_id = args.get("presentation_id")
            s_title = args.get("title", "")
            s_body = args.get("body_text", "")
            if not p_id:
                raise ValueError("Missing 'presentation_id'")
            creds = self._get_credentials()
            creds.refresh(Request())

            import uuid
            slide_obj_id = f"slide_{uuid.uuid4().hex[:12]}"
            batch_url = f"https://slides.googleapis.com/v1/presentations/{p_id}:batchUpdate"

            create_req = {
                "requests": [
                    {
                        "createSlide": {
                            "objectId": slide_obj_id,
                            "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"}
                        }
                    }
                ]
            }
            r_c = requests.post(batch_url, headers={"Authorization": f"Bearer {creds.token}"}, json=create_req)
            if r_c.status_code != 200:
                raise RuntimeError(f"Slides create error: {r_c.text}")

            get_url = f"https://slides.googleapis.com/v1/presentations/{p_id}"
            r_g = requests.get(get_url, headers={"Authorization": f"Bearer {creds.token}"})
            p_data = r_g.json()
            title_elem_id = None
            body_elem_id = None
            for s in p_data.get("slides", []):
                if s.get("objectId") == slide_obj_id:
                    for pe in s.get("pageElements", []):
                        p_type = pe.get("shape", {}).get("placeholder", {}).get("type")
                        if p_type == "TITLE":
                            title_elem_id = pe.get("objectId")
                        elif p_type == "BODY":
                            body_elem_id = pe.get("objectId")

            insert_requests = []
            if title_elem_id and s_title:
                insert_requests.append({
                    "insertText": {"objectId": title_elem_id, "text": s_title}
                })
            if body_elem_id and s_body:
                insert_requests.append({
                    "insertText": {"objectId": body_elem_id, "text": s_body}
                })
            if insert_requests:
                r_ins = requests.post(batch_url, headers={"Authorization": f"Bearer {creds.token}"}, json={"requests": insert_requests})
                if r_ins.status_code != 200:
                    raise RuntimeError(f"Slides insert error: {r_ins.text}")

            return {"status": "slide_created", "presentation_id": p_id, "slide_id": slide_obj_id, "title": s_title}

        raise ValueError(f"Unknown tool: '{tool_name}'")

    async def handle_request(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {}) or {}

        if method == "initialize":
            return make_result_response(
                req_id,
                {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": self.name, "version": self.version},
                },
            )
        elif method == "notifications/initialized":
            return None
        elif method == "ping":
            return make_result_response(req_id, {})
        elif method == "tools/list":
            return make_result_response(req_id, {"tools": self.get_tool_definitions()})
        elif method == "tools/call":
            t_name = params.get("name")
            args = params.get("arguments", {}) or {}
            if not isinstance(t_name, str):
                return make_error_response(req_id, -32602, "Invalid params: 'name' must be a string")
            try:
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, self.handle_tool_call, t_name, args)
                return make_result_response(
                    req_id,
                    {"content": [{"type": "text", "text": json.dumps(res, indent=2, default=str)}]},
                )
            except Exception as e:
                return make_result_response(
                    req_id,
                    {"isError": True, "content": [{"type": "text", "text": f"Error: {e}"}]},
                )
        return make_error_response(req_id, METHOD_NOT_FOUND, f"Unknown method: '{method}'")

    async def run(self):
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line_str = line.strip()
            if not line_str:
                continue
            try:
                req = json.loads(line_str)
                resp = await self.handle_request(req)
                if resp is not None:
                    sys.stdout.write(json.dumps(resp) + "\n")
                    sys.stdout.flush()
            except Exception as e:
                err = make_error_response(None, PARSE_ERROR, str(e))
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = GoogleSheetsMcpServer()
    asyncio.run(server.run())
