//+------------------------------------------------------------------+
//|  AIAgent_EA.mq5                                                  |
//|  Dead-Man's Switch + SL/TP Guardian EA for AI Trading Agent      |
//|                                                                  |
//|  Per spec §10:                                                   |
//|  "EA memantau 'heartbeat' dari backend. Kalau heartbeat berhenti |
//|   dalam durasi tertentu, EA otomatis menutup semua posisi atau   |
//|   menghentikan trading baru."                                    |
//|                                                                  |
//|  Roles of this EA (NOT a decision-maker):                        |
//|  1. Dead-man's switch: reads heartbeat file written by Python    |
//|     backend. If heartbeat is stale > HEARTBEAT_TIMEOUT_SECONDS,  |
//|     closes all AI-managed positions.                             |
//|  2. SL/TP Guardian: ensures every AI-managed position (magic     |
//|     number 20250101) always has SL set. If SL is missing (e.g.   |
//|     due to broker rejection), EA re-applies it from position     |
//|     comment data.                                                |
//|  3. Heartbeat writer: writes its own heartbeat file so the       |
//|     Python backend knows the EA is alive.                        |
//+------------------------------------------------------------------+
#property copyright   "AIAgent"
#property version     "1.00"
#property strict

//--- EA Parameters
input int    HEARTBEAT_TIMEOUT_SECONDS = 600;   // 10 minutes — accommodates PC restart + MT5 reconnect
input int    CHECK_INTERVAL_SECONDS    = 30;    // How often EA checks heartbeat & SL
input string HEARTBEAT_FILE_PYTHON     = "ai_agent_heartbeat.txt";      // Written by Python
input string HEARTBEAT_FILE_EA         = "ea_heartbeat.txt";            // Written by this EA
input int    AI_MAGIC_NUMBER           = 20250101;  // Magic number used by Python's place_order
input bool   ENABLE_DEAD_MANS_SWITCH   = true;
input bool   ENABLE_SL_GUARDIAN        = true;

#define CLAUDE_MAGIC_NUMBER AI_MAGIC_NUMBER

//--- State variables
datetime lastHeartbeatTime = 0;
datetime lastCheckTime     = 0;
bool     emergencyClosed   = false;

//+------------------------------------------------------------------+
//| Expert initialization function                                    |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("[AIAgent EA] Initialized.");
    Print("[AIAgent EA] Heartbeat timeout: ", HEARTBEAT_TIMEOUT_SECONDS, "s");
    Print("[AIAgent EA] Magic number: ", AI_MAGIC_NUMBER);
    Print("[AIAgent EA] Dead-man switch: ", ENABLE_DEAD_MANS_SWITCH ? "ON" : "OFF");

    // Write initial EA heartbeat
    WriteEAHeartbeat();

    // Set timer for periodic checks
    EventSetTimer(CHECK_INTERVAL_SECONDS);
    return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                  |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("[AIAgent EA] Deinitialized. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Timer event — primary execution loop for heartbeat & checks       |
//+------------------------------------------------------------------+
void OnTimer()
{
    datetime now = TimeGMT();

    // Write EA heartbeat to confirm EA is running
    WriteEAHeartbeat();

    // Check Python backend heartbeat
    if(ENABLE_DEAD_MANS_SWITCH)
    {
        CheckPythonHeartbeat(now);
    }

    // SL Guardian check
    if(ENABLE_SL_GUARDIAN)
    {
        EnforceSLOnAIPositions();
    }
}

//+------------------------------------------------------------------+
//| Check Python backend heartbeat file                               |
//+------------------------------------------------------------------+
void CheckPythonHeartbeat(datetime now)
{
    if(!FileIsExist(HEARTBEAT_FILE_PYTHON, FILE_COMMON))
    {
        // File doesn't exist yet — not an error on first run
        Print("[AIAgent EA] Heartbeat file not found: ", HEARTBEAT_FILE_PYTHON);
        if(lastHeartbeatTime > 0)
        {
            long staleSeconds = (long)(now - lastHeartbeatTime);
            if(staleSeconds > HEARTBEAT_TIMEOUT_SECONDS && !emergencyClosed)
            {
                Print("[AIAgent EA] HEARTBEAT FILE MISSING AND TIMEOUT EXCEEDED! CLOSING ALL AI POSITIONS");
                EmergencyCloseAllAIPositions();
                emergencyClosed = true;
            }
        }
        return;
    }

    int handle = FileOpen(HEARTBEAT_FILE_PYTHON, FILE_READ | FILE_TXT | FILE_COMMON | FILE_ANSI);
    if(handle == INVALID_HANDLE)
    {
        Print("[AIAgent EA] Cannot open heartbeat file.");
        if(lastHeartbeatTime > 0 && (long)(now - lastHeartbeatTime) > HEARTBEAT_TIMEOUT_SECONDS && !emergencyClosed)
        {
            Print("[AIAgent EA] HEARTBEAT READ TIMEOUT! CLOSING ALL AI POSITIONS");
            EmergencyCloseAllAIPositions();
            emergencyClosed = true;
        }
        return;
    }

    string content = FileReadString(handle);
    FileClose(handle);

    // Parse Unix timestamp from file content (Python writes: "1722900000")
    StringTrimRight(content);
    StringTrimLeft(content);
    datetime heartbeatTs = (datetime)StringToInteger(content);

    if(heartbeatTs <= 0)
    {
        Print("[AIAgent EA] Invalid heartbeat timestamp: ", content);
        if(lastHeartbeatTime > 0 && (long)(now - lastHeartbeatTime) > HEARTBEAT_TIMEOUT_SECONDS && !emergencyClosed)
        {
            Print("[AIAgent EA] HEARTBEAT INVALID CONTENT TIMEOUT! CLOSING ALL AI POSITIONS");
            EmergencyCloseAllAIPositions();
            emergencyClosed = true;
        }
        return;
    }

    long staleSeconds = (long)(now - heartbeatTs);

    if(staleSeconds > HEARTBEAT_TIMEOUT_SECONDS)
    {
        if(!emergencyClosed)
        {
            Print("[AIAgent EA] HEARTBEAT TIMEOUT! Last beat: ", TimeToString(heartbeatTs),
                  " | Stale for: ", staleSeconds, "s | CLOSING ALL AI POSITIONS");
    
            EmergencyCloseAllAIPositions();
            emergencyClosed = true;
        }
    }
    else
    {
        lastHeartbeatTime = heartbeatTs;
        if(emergencyClosed)
        {
            Print("[AIAgent EA] Heartbeat restored. Resetting emergency closed flag.");
            emergencyClosed = false;
        }
    }
}

//+------------------------------------------------------------------+
//| Get symbol filling mode supported by broker                       |
//+------------------------------------------------------------------+
ENUM_ORDER_TYPE_FILLING GetSymbolFilling(const string sym)
{
    long filling = SymbolInfoInteger(sym, SYMBOL_FILLING_MODE);
    if((filling & SYMBOL_FILLING_FOK) != 0)
        return ORDER_FILLING_FOK;
    if((filling & SYMBOL_FILLING_IOC) != 0)
        return ORDER_FILLING_IOC;
    return ORDER_FILLING_RETURN;
}

//+------------------------------------------------------------------+
//| Emergency close all AI-managed positions                          |
//+------------------------------------------------------------------+
void EmergencyCloseAllAIPositions()
{
    int closedCount = 0;
    int failedCount = 0;
    int maxRetries = 3;

    for(int attempt = 1; attempt <= maxRetries; attempt++)
    {
        failedCount = 0;
        int total = PositionsTotal();

        for(int i = total - 1; i >= 0; i--)
        {
            ulong ticket = PositionGetTicket(i);
            if(!PositionSelectByTicket(ticket)) continue;

            // Only close positions with our magic number
            if((int)PositionGetInteger(POSITION_MAGIC) != AI_MAGIC_NUMBER) continue;

            string sym = PositionGetString(POSITION_SYMBOL);
            double vol = PositionGetDouble(POSITION_VOLUME);
            ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

            MqlTradeRequest  req  = {};
            MqlTradeResult   res  = {};
            req.action   = TRADE_ACTION_DEAL;
            req.symbol   = sym;
            req.volume   = vol;
            req.type     = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            req.position = ticket;
            
            double bid = SymbolInfoDouble(sym, SYMBOL_BID);
            double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
            if(bid == 0.0 || ask == 0.0)
            {
                MqlTick tick;
                if(SymbolInfoTick(sym, tick))
                {
                    bid = tick.bid;
                    ask = tick.ask;
                }
            }
            
            req.price        = (posType == POSITION_TYPE_BUY) ? bid : ask;
            req.deviation    = 50;
            req.type_filling = GetSymbolFilling(sym);
            req.comment      = "DeadManSwitch";
            req.magic        = AI_MAGIC_NUMBER;

            if(OrderSend(req, res) && res.retcode == TRADE_RETCODE_DONE)
            {
                Print("[AIAgent EA] Emergency closed ticket=", ticket, " sym=", sym);
                closedCount++;
            }
            else
            {
                Print("[AIAgent EA] FAILED to close ticket=", ticket,
                      " retcode=", res.retcode, " comment=", res.comment);
                failedCount++;
            }
        }
        
        if(failedCount == 0) break;
        
        if(attempt < maxRetries)
        {
            Print("[AIAgent EA] Retrying emergency close in 1s. Remaining failed: ", failedCount);
            Sleep(1000);
        }
    }

    Print("[AIAgent EA] Emergency close done: closed=", closedCount,
          " failed=", failedCount);
}

//+------------------------------------------------------------------+
//| Ensure every AI position has a valid SL set                       |
//+------------------------------------------------------------------+
void EnforceSLOnAIPositions()
{
    int total = PositionsTotal();
    for(int i = total - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if(!PositionSelectByTicket(ticket)) continue;
        if((int)PositionGetInteger(POSITION_MAGIC) != AI_MAGIC_NUMBER) continue;

        double sl = PositionGetDouble(POSITION_SL);

        // If SL is 0 (not set), this is dangerous — log it
        if(sl == 0.0)
        {
            string sym = PositionGetString(POSITION_SYMBOL);
            Print("[AIAgent EA] CRITICAL: Position ", ticket, " (", sym,
                  ") has NO stop loss! CLOSING POSITION IMMEDIATELY.");
            
            double vol = PositionGetDouble(POSITION_VOLUME);
            ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);

            MqlTradeRequest  req  = {};
            MqlTradeResult   res  = {};
            req.action   = TRADE_ACTION_DEAL;
            req.symbol   = sym;
            req.volume   = vol;
            req.type     = (posType == POSITION_TYPE_BUY) ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
            req.position = ticket;
            
            double bid = SymbolInfoDouble(sym, SYMBOL_BID);
            double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
            if(bid == 0.0 || ask == 0.0)
            {
                MqlTick tick;
                if(SymbolInfoTick(sym, tick))
                {
                    bid = tick.bid;
                    ask = tick.ask;
                }
            }
            
            req.price        = (posType == POSITION_TYPE_BUY) ? bid : ask;
            req.deviation    = 30;
            req.type_filling = GetSymbolFilling(sym);
            req.comment      = "GuardianClose";
            req.magic        = AI_MAGIC_NUMBER;

            if(!OrderSend(req, res) || res.retcode != TRADE_RETCODE_DONE)
            {
                Print("[AIAgent EA] FAILED to emergency close ticket=", ticket,
                      " retcode=", res.retcode);
            }
        }
    }
}

// Backward-compatible function aliases
void EmergencyCloseAllClaudePositions() { EmergencyCloseAllAIPositions(); }
void EnforceSLOnClaudePositions() { EnforceSLOnAIPositions(); }

//+------------------------------------------------------------------+
//| Write EA's own heartbeat file                                     |
//+------------------------------------------------------------------+
void WriteEAHeartbeat()
{
    int handle = FileOpen(HEARTBEAT_FILE_EA, FILE_WRITE | FILE_TXT | FILE_COMMON | FILE_ANSI);
    if(handle == INVALID_HANDLE)
    {
        Print("[AIAgent EA] Cannot write EA heartbeat file.");
        return;
    }
    FileWriteString(handle, IntegerToString((long)TimeGMT()));
    FileClose(handle);
}

//+------------------------------------------------------------------+
//| Tick event — not used for trading decisions                       |
//+------------------------------------------------------------------+
void OnTick()
{
    // EA does not make trading decisions on ticks.
    // All decisions come from the Python backend.
}
