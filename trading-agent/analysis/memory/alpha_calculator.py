import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from database.models import DXYData, PriceOHLCV

logger = logging.getLogger(__name__)

class AlphaCalculator:
    """
    Kalkulator untuk menghitung Alpha (Return Asset vs Benchmark).
    
    Benchmarks:
    - EURUSD/GBPUSD/AUDUSD/NZDUSD -> DXY inverse (-1.0)
    - USDJPY/USDCHF/USDCAD -> DXY (+1.0)
    - XAUUSD -> DXY inverse
    - XAGUSD -> XAUUSD
    - BTCUSD -> flat 0%
    - ETHUSD -> BTCUSD
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_benchmark_return(self, benchmark_name: str, entry_time: datetime, exit_time: datetime) -> float:
        """Mendapatkan return benchmark antara entry_time dan exit_time dalam persentase."""
        if benchmark_name == 'FLAT':
            return 0.0

        if benchmark_name == 'DXY':
            # Jika trade intraday (buka & tutup pada hari yang sama), coba gunakan proxy H1 EURUSD terbalik
            if entry_time.date() == exit_time.date():
                stmt_eur_entry = select(PriceOHLCV.close).where(
                    and_(PriceOHLCV.symbol == 'EURUSD', PriceOHLCV.timeframe == 'H1', PriceOHLCV.timestamp <= entry_time)
                ).order_by(PriceOHLCV.timestamp.desc()).limit(1)
                stmt_eur_exit = select(PriceOHLCV.close).where(
                    and_(PriceOHLCV.symbol == 'EURUSD', PriceOHLCV.timeframe == 'H1', PriceOHLCV.timestamp <= exit_time)
                ).order_by(PriceOHLCV.timestamp.desc()).limit(1)
                eur_e = (await self.session.execute(stmt_eur_entry)).scalar_one_or_none()
                eur_x = (await self.session.execute(stmt_eur_exit)).scalar_one_or_none()
                if eur_e and eur_x and eur_e > 0:
                    eur_ret = ((eur_x - eur_e) / eur_e) * 100.0
                    return -eur_ret  # Inverse EUR return as intraday USD strength proxy

            # Query DXYData harian
            stmt_entry = select(DXYData.close).where(DXYData.date <= entry_time).order_by(DXYData.date.desc()).limit(1)
            stmt_exit = select(DXYData.close).where(DXYData.date <= exit_time).order_by(DXYData.date.desc()).limit(1)
            
            entry_res = await self.session.execute(stmt_entry)
            exit_res = await self.session.execute(stmt_exit)
            
            entry_price = entry_res.scalar_one_or_none()
            exit_price = exit_res.scalar_one_or_none()

            if entry_price and exit_price and entry_price > 0:
                return ((exit_price - entry_price) / entry_price) * 100.0
            return 0.0

        # Untuk XAUUSD, BTCUSD, dsb gunakan PriceOHLCV H1
        stmt_entry = select(PriceOHLCV.close).where(
            and_(PriceOHLCV.symbol == benchmark_name, PriceOHLCV.timeframe == 'H1', PriceOHLCV.timestamp <= entry_time)
        ).order_by(PriceOHLCV.timestamp.desc()).limit(1)
        
        stmt_exit = select(PriceOHLCV.close).where(
            and_(PriceOHLCV.symbol == benchmark_name, PriceOHLCV.timeframe == 'H1', PriceOHLCV.timestamp <= exit_time)
        ).order_by(PriceOHLCV.timestamp.desc()).limit(1)

        entry_res = await self.session.execute(stmt_entry)
        exit_res = await self.session.execute(stmt_exit)
        
        entry_price = entry_res.scalar_one_or_none()
        exit_price = exit_res.scalar_one_or_none()

        if entry_price and exit_price and entry_price > 0:
            return ((exit_price - entry_price) / entry_price) * 100.0
        return 0.0

    async def calculate_alpha(
        self, 
        symbol: str, 
        direction: str,
        entry_time: datetime, 
        exit_time: datetime, 
        asset_return_pct: float
    ) -> dict:
        """
        Menghitung alpha untuk trade yang telah close.
        Returns dict dengan keys: benchmark_name, benchmark_return, alpha_return
        """
        symbol_upper = symbol.upper()
        
        benchmark_name = 'DXY'
        benchmark_multiplier = 1.0

        if symbol_upper in ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'XAUUSD']:
            benchmark_name = 'DXY'
            benchmark_multiplier = -1.0
        elif symbol_upper in ['USDJPY', 'USDCHF', 'USDCAD']:
            benchmark_name = 'DXY'
            benchmark_multiplier = 1.0
        elif symbol_upper == 'XAGUSD':
            benchmark_name = 'XAUUSD'
            benchmark_multiplier = 1.0
        elif symbol_upper == 'BTCUSD':
            benchmark_name = 'FLAT'
            benchmark_multiplier = 1.0
        elif symbol_upper == 'ETHUSD':
            benchmark_name = 'BTCUSD'
            benchmark_multiplier = 1.0
        else:
            # Fallback jika tidak diketahui, bandingkan dengan DXY (karena mayoritas dipengaruhi USD)
            benchmark_name = 'DXY'
            benchmark_multiplier = 1.0

        raw_benchmark_return = await self.get_benchmark_return(benchmark_name, entry_time, exit_time)
        
        # Sesuaikan benchmark return berdasarkan arah korelasi dan arah trade
        # Jika trade SELL, maka return asset dibalik (karena harga turun = profit)
        # Tapi asset_return_pct sudah merupakan profit/loss (positif jika profit), jadi kita tidak mengubah asset_return_pct.
        # Kita hanya perlu menyesuaikan benchmark_return dari sudut pandang direction yang sama.
        # Jika kita BUY EURUSD, dan DXY turun 1%, maka benchmark return efektif = -(-1%) = 1%
        # Tapi jika kita SELL EURUSD (berharap EURUSD turun), dan DXY turun 1% (maka EURUSD seharusnya naik 1%), benchmark efektif untuk posisi short ini adalah -1%.
        
        # Rumus benchmark_eff_return: 
        # return_mentah_benchmark * multiplier_korelasi * arah_posisi (BUY=1, SELL=-1)
        direction_mult = 1.0 if direction.upper() == 'BUY' else -1.0
        eff_benchmark_return = raw_benchmark_return * benchmark_multiplier * direction_mult

        alpha = asset_return_pct - eff_benchmark_return

        return {
            "benchmark_name": benchmark_name,
            "benchmark_return": eff_benchmark_return,
            "alpha_return": alpha
        }
