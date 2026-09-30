# ==============================================================================
# File: analysis/mcp/servers/excel_server.py
# Description: Built-in Excel and CSV Tabular MCP Server
# Provides safe inspection, querying, reading, and appending to spreadsheet files.
# ==============================================================================

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import openpyxl

from analysis.mcp.protocol import (
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    LATEST_PROTOCOL_VERSION,
    make_error_response,
    make_result_response,
)


class ExcelMcpServer:
    """Stdio-based MCP Server for Excel (.xlsx, .xls) and CSV spreadsheet files."""

    def __init__(self):
        self.name = "excel-tabular-server"
        self.version = "1.0.0"

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "excel_list_sheets",
                "description": "List all sheet/tab names in an Excel file (.xlsx, .xls) or verify CSV file.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute or relative path to the .xlsx, .xls, or .csv file.",
                        }
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "excel_read_sheet",
                "description": "Read rows from an Excel sheet or CSV file with optional pagination and column filtering.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the spreadsheet file.",
                        },
                        "sheet_name": {
                            "type": "string",
                            "description": "Optional sheet name. If omitted, first sheet is read.",
                        },
                        "start_row": {
                            "type": "integer",
                            "description": "1-based starting row offset (default: 1).",
                        },
                        "max_rows": {
                            "type": "integer",
                            "description": "Maximum number of rows to return (default: 50, max: 200).",
                        },
                        "columns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of column names to select.",
                        },
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "excel_append_row",
                "description": "Append a new row of data to an existing Excel sheet or CSV file.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the spreadsheet file.",
                        },
                        "sheet_name": {
                            "type": "string",
                            "description": "Sheet name for Excel. Ignored for CSV.",
                        },
                        "row_data": {
                            "type": "object",
                            "description": "Key-value dictionary mapping column headers to cell values.",
                        },
                    },
                    "required": ["file_path", "row_data"],
                },
            },
            {
                "name": "excel_create_sheet",
                "description": "Create a new Excel file or add a new sheet with specified header columns.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the .xlsx file.",
                        },
                        "sheet_name": {
                            "type": "string",
                            "description": "Name for the new sheet.",
                        },
                        "headers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of header column names.",
                        },
                    },
                    "required": ["file_path", "sheet_name", "headers"],
                },
            },
        ]

    def _resolve_path(self, file_path: str) -> Path:
        p = Path(os.path.expandvars(os.path.expanduser(file_path))).resolve()
        return p

    def handle_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        raw_path = arguments.get("file_path", "").strip()
        if not raw_path:
            raise ValueError("'file_path' is required")
        path = self._resolve_path(raw_path)

        if tool_name == "excel_list_sheets":
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            if path.suffix.lower() == ".csv":
                return {"file_type": "csv", "sheets": ["default"], "path": str(path)}
            wb = openpyxl.load_workbook(path, read_only=True)
            sheets = wb.sheetnames
            wb.close()
            return {"file_type": "excel", "sheets": sheets, "path": str(path)}

        elif tool_name == "excel_read_sheet":
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")

            sheet_name = arguments.get("sheet_name")
            start_row = max(1, int(arguments.get("start_row", 1)))
            max_rows = min(max(1, int(arguments.get("max_rows", 50))), 200)
            columns = arguments.get("columns")

            skiprows = range(1, start_row) if start_row > 1 else None

            if path.suffix.lower() == ".csv":
                df = pd.read_csv(path, skiprows=skiprows, nrows=max_rows)
            else:
                target_sheet = sheet_name if sheet_name else 0
                df = pd.read_excel(path, sheet_name=target_sheet, skiprows=skiprows, nrows=max_rows)

            if columns and isinstance(columns, list):
                valid_cols = [c for c in columns if c in df.columns]
                if valid_cols:
                    df = df[valid_cols]

            df = df.where(pd.notnull(df), None)
            records = df.to_dict(orient="records")

            return {
                "file_path": str(path),
                "sheet": sheet_name or "Sheet1",
                "row_count": len(records),
                "columns": list(df.columns),
                "data": records,
            }

        elif tool_name == "excel_append_row":
            row_data = arguments.get("row_data", {})
            if not isinstance(row_data, dict):
                raise ValueError("'row_data' must be a JSON dictionary mapping column names to values")

            sheet_name = arguments.get("sheet_name") or "Sheet1"

            if path.suffix.lower() == ".csv":
                if not path.exists():
                    df = pd.DataFrame([row_data])
                    df.to_csv(path, index=False)
                else:
                    df = pd.DataFrame([row_data])
                    df.to_csv(path, mode="a", header=False, index=False)
                return {"status": "success", "file_path": str(path), "appended": row_data}

            # Excel .xlsx append
            if not path.exists():
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = sheet_name
                headers = list(row_data.keys())
                ws.append(headers)
                ws.append([row_data.get(h) for h in headers])
                wb.save(path)
                return {"status": "created_and_appended", "file_path": str(path), "sheet": sheet_name, "appended": row_data}

            wb = openpyxl.load_workbook(path)
            if sheet_name not in wb.sheetnames:
                ws = wb.create_sheet(title=sheet_name)
                headers = list(row_data.keys())
                ws.append(headers)
                ws.append([row_data.get(h) for h in headers])
            else:
                ws = wb[sheet_name]
                header_row = [cell.value for cell in ws[1]]
                if not any(header_row):
                    headers = list(row_data.keys())
                    ws.append(headers)
                    header_row = headers

                row_values = []
                for h in header_row:
                    row_values.append(row_data.get(h, ""))
                ws.append(row_values)

            wb.save(path)
            return {"status": "appended", "file_path": str(path), "sheet": sheet_name, "appended": row_data}

        elif tool_name == "excel_create_sheet":
            sheet_name = arguments.get("sheet_name", "Sheet1").strip()
            headers = arguments.get("headers", [])
            if not isinstance(headers, list):
                raise ValueError("'headers' must be a list of strings")

            if not path.exists():
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = sheet_name
                ws.append(headers)
                wb.save(path)
                return {"status": "created_workbook", "file_path": str(path), "sheet": sheet_name, "headers": headers}

            wb = openpyxl.load_workbook(path)
            if sheet_name in wb.sheetnames:
                return {"status": "exists", "file_path": str(path), "sheet": sheet_name, "message": "Sheet already exists"}
            ws = wb.create_sheet(title=sheet_name)
            ws.append(headers)
            wb.save(path)
            return {"status": "created_sheet", "file_path": str(path), "sheet": sheet_name, "headers": headers}

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
                res = self.handle_tool_call(t_name, args)
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
    server = ExcelMcpServer()
    asyncio.run(server.run())
