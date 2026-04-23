import logging
import os
import sys
from dotenv import load_dotenv

import httpx
from ..accounts import infer_account_type
from ..analytics.bollinger import get_bollinger_bands as analyze_bollinger_bands
from ..analytics.portfolio import (
    get_latest_portfolio_summary as analyze_latest_portfolio_summary,
    get_portfolio_daily_change as analyze_portfolio_daily_change,
    get_portfolio_anomalies as analyze_portfolio_anomalies,
    get_portfolio_trend as analyze_portfolio_trend,
)
from ..auth import get_access_token, get_hashkey, get_token_status as inspect_token_status
from ..clients.kis import AUTH_TYPE, CONTENT_TYPE, DOMAIN, VIRTUAL_DOMAIN
from .account import fetch_balance_snapshot
from .. import db as kisdb

# 로깅 설정: 반드시 stderr로 출력. 기본값은 계좌번호가 포함된 HTTP URL을 남기지 않도록 INFO로 둔다.
logging.basicConfig(
    level=os.environ.get("KIS_LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("mcp-server")

# Load environment variables from .env file before resolving runtime paths.
load_dotenv()

# API paths
STOCK_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"  # 현재가조회
ORDER_PATH = "/uapi/domestic-stock/v1/trading/order-cash"  # 현금주문
ORDER_LIST_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"  # 일별주문체결조회
ORDER_DETAIL_PATH = "/uapi/domestic-stock/v1/trading/inquire-ccnl"  # 주문체결내역조회
STOCK_INFO_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-price"  # 일별주가조회
STOCK_HISTORY_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"  # 주식일별주가조회
STOCK_ASK_PATH = "/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"  # 주식호가조회

# 해외주식 API 경로
OVERSEAS_STOCK_PRICE_PATH = "/uapi/overseas-price/v1/quotations/price"
OVERSEAS_ORDER_PATH = "/uapi/overseas-stock/v1/trading/order"
OVERSEAS_BALANCE_PATH = "/uapi/overseas-stock/v1/trading/inquire-balance"
OVERSEAS_ORDER_LIST_PATH = "/uapi/overseas-stock/v1/trading/inquire-daily-ccld"

# Market codes for overseas stock
MARKET_CODES = {
    "NASD": "나스닥",
    "NYSE": "뉴욕",
    "AMEX": "아멕스",
    "SEHK": "홍콩",
    "SHAA": "중국상해",
    "SZAA": "중국심천",
    "TKSE": "일본",
    "HASE": "베트남 하노이",
    "VNSE": "베트남 호치민"
}


def _current_account_id(account_id: str = "") -> str:
    return account_id or os.environ.get("KIS_CANO", "unknown")


def _order_tools_enabled() -> bool:
    return os.environ.get("KIS_ENABLE_ORDER_TOOLS", "").lower() == "true"


def _disabled_order_response() -> dict:
    return {
        "status": "disabled",
        "message": "주문 tool은 기본 비활성입니다. KIS_ENABLE_ORDER_TOOLS=true 설정 후 명시적으로 다시 시도하세요.",
    }


class TrIdManager:
    """Transaction ID manager for Korea Investment & Securities API"""
    
    # 실전계좌용 TR_ID
    REAL = {
        # 국내주식
        "balance": "TTTC8434R",  # 잔고조회
        "pension_balance": "TTTC2208R",  # 퇴직연금 잔고조회
        "price": "FHKST01010100",  # 현재가조회
        "buy": "TTTC0802U",  # 주식매수
        "sell": "TTTC0801U",  # 주식매도
        "order_list": "TTTC8001R",  # 일별주문체결조회
        "order_detail": "TTTC8036R",  # 주문체결내역조회
        "stock_info": "FHKST01010400",  # 일별주가조회
        "stock_history": "FHKST03010200",  # 주식일별주가조회
        "stock_ask": "FHKST01010200",  # 주식호가조회
        
        # 해외주식
        "us_buy": "TTTT1002U",      # 미국 매수 주문
        "us_sell": "TTTT1006U",     # 미국 매도 주문
        "jp_buy": "TTTS0308U",      # 일본 매수 주문
        "jp_sell": "TTTS0307U",     # 일본 매도 주문
        "sh_buy": "TTTS0202U",      # 상해 매수 주문
        "sh_sell": "TTTS1005U",     # 상해 매도 주문
        "hk_buy": "TTTS1002U",      # 홍콩 매수 주문
        "hk_sell": "TTTS1001U",     # 홍콩 매도 주문
        "sz_buy": "TTTS0305U",      # 심천 매수 주문
        "sz_sell": "TTTS0304U",     # 심천 매도 주문
        "vn_buy": "TTTS0311U",      # 베트남 매수 주문
        "vn_sell": "TTTS0310U",     # 베트남 매도 주문
    }
    
    # 모의계좌용 TR_ID
    VIRTUAL = {
        # 국내주식
        "balance": "VTTC8434R",  # 잔고조회
        "pension_balance": "TTTC2208R",  # 퇴직연금 잔고조회 (모의 없음)
        "price": "FHKST01010100",  # 현재가조회
        "buy": "VTTC0802U",  # 주식매수
        "sell": "VTTC0801U",  # 주식매도
        "order_list": "VTTC8001R",  # 일별주문체결조회
        "order_detail": "VTTC8036R",  # 주문체결내역조회
        "stock_info": "FHKST01010400",  # 일별주가조회
        "stock_history": "FHKST03010200",  # 주식일별주가조회
        "stock_ask": "FHKST01010200",  # 주식호가조회
        
        # 해외주식
        "us_buy": "VTTT1002U",      # 미국 매수 주문
        "us_sell": "VTTT1001U",     # 미국 매도 주문
        "jp_buy": "VTTS0308U",      # 일본 매수 주문
        "jp_sell": "VTTS0307U",     # 일본 매도 주문
        "sh_buy": "VTTS0202U",      # 상해 매수 주문
        "sh_sell": "VTTS1005U",     # 상해 매도 주문
        "hk_buy": "VTTS1002U",      # 홍콩 매수 주문
        "hk_sell": "VTTS1001U",     # 홍콩 매도 주문
        "sz_buy": "VTTS0305U",      # 심천 매수 주문
        "sz_sell": "VTTS0304U",     # 심천 매도 주문
        "vn_buy": "VTTS0311U",      # 베트남 매수 주문
        "vn_sell": "VTTS0310U",     # 베트남 매도 주문
    }
    
    @classmethod
    def get_tr_id(cls, operation: str) -> str:
        """
        Get transaction ID for the given operation
        
        Args:
            operation: Operation type ('balance', 'price', 'buy', 'sell', etc.)
            
        Returns:
            str: Transaction ID for the operation
        """
        is_real_account = os.environ.get("KIS_ACCOUNT_TYPE", "REAL").upper() == "REAL"
        tr_id_map = cls.REAL if is_real_account else cls.VIRTUAL
        return tr_id_map.get(operation)
    
    @classmethod
    def get_domain(cls, operation: str) -> str:
        """
        Get domain for the given operation
        
        Args:
            operation: Operation type ('balance', 'price', 'buy', 'sell', etc.)
            
        Returns:
            str: Domain URL for the operation
        """
        is_real_account = os.environ.get("KIS_ACCOUNT_TYPE", "REAL").upper() == "REAL"
        
        # 잔고조회는 실전/모의 계좌별로 다른 도메인 사용
        if operation == "balance":
            return DOMAIN if is_real_account else VIRTUAL_DOMAIN
            
        # 조회 API는 실전/모의 동일한 도메인 사용
        if operation in ["price", "stock_info", "stock_history", "stock_ask"]:
            return DOMAIN
            
        # 거래 API는 계좌 타입에 따라 다른 도메인 사용
        return DOMAIN if is_real_account else VIRTUAL_DOMAIN

async def inquery_stock_price(symbol: str):
    """
    Get current stock price information from Korea Investment & Securities
    
    Args:
        symbol: Stock symbol (e.g. "005930" for Samsung Electronics)
        
    Returns:
        Dictionary containing stock price information including:
        - stck_prpr: Current price
        - prdy_vrss: Change from previous day
        - prdy_vrss_sign: Change direction (+/-)
        - prdy_ctrt: Change rate (%)
        - acml_vol: Accumulated volume
        - acml_tr_pbmn: Accumulated trade value
        - hts_kor_isnm: Stock name in Korean
        - stck_mxpr: High price of the day
        - stck_llam: Low price of the day
        - stck_oprc: Opening price
        - stck_prdy_clpr: Previous day's closing price
    """
    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        response = await client.get(
            f"{TrIdManager.get_domain('price')}{STOCK_PRICE_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": TrIdManager.get_tr_id("price")
            },
            params={
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": symbol
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get stock price: {response.text}")
        
        return response.json()["output"]

async def inquery_balance():
    """
    Get current stock balance information from Korea Investment & Securities.
    Automatically routes to the pension API only when KIS_ACNT_PRDT_CD is "29"
    (IRP). Pension savings ("22") uses the standard balance API.
    """
    return await fetch_balance_snapshot(save_snapshot=True)

async def order_stock(symbol: str, quantity: int, price: int, order_type: str):
    """
    Order stock (buy/sell) from Korea Investment & Securities
    
    Args:
        symbol: Stock symbol (e.g. "005930")
        quantity: Order quantity
        price: Order price (0 for market price)
        order_type: Order type ("buy" or "sell", case-insensitive)
        
    Returns:
        Dictionary containing order information
    """
    if not _order_tools_enabled():
        return _disabled_order_response()

    # Normalize order_type to lowercase
    order_type = order_type.lower()
    if order_type not in ["buy", "sell"]:
        raise ValueError('order_type must be either "buy" or "sell"')

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        
        # Prepare request data
        request_data = {
            "CANO": os.environ["KIS_CANO"],  # 계좌번호
            "ACNT_PRDT_CD": "01",  # 계좌상품코드
            "PDNO": symbol,  # 종목코드
            "ORD_DVSN": "01" if price == 0 else "00",  # 주문구분 (01: 시장가, 00: 지정가)
            "ORD_QTY": str(quantity),  # 주문수량
            "ORD_UNPR": str(price),  # 주문단가
        }
        
        # Get hashkey
        hashkey = await get_hashkey(client, TrIdManager.get_domain(order_type), token, request_data)
        
        response = await client.post(
            f"{TrIdManager.get_domain(order_type)}{ORDER_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": TrIdManager.get_tr_id(order_type),
                "hashkey": hashkey
            },
            json=request_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to order stock: {response.text}")
        
        return response.json()

async def inquery_order_list(
    start_date: str,
    end_date: str,
    save_history: bool = False,
    return_metadata: bool = False,
):
    """
    Get daily order list from Korea Investment & Securities
    
    Args:
        start_date: Start date (YYYYMMDD)
        end_date: End date (YYYYMMDD)
        
    Returns:
        Dictionary containing order list information
    """
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")
    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        
        # Prepare request data
        request_data = {
            "CANO": os.environ["KIS_CANO"],  # 계좌번호
            "ACNT_PRDT_CD": acnt_prdt_cd,  # 계좌상품코드
            "INQR_STRT_DT": start_date,  # 조회시작일자
            "INQR_END_DT": end_date,  # 조회종료일자
            "SLL_BUY_DVSN_CD": "00",  # 매도매수구분
            "INQR_DVSN": "00",  # 조회구분
            "PDNO": "",  # 종목코드
            "CCLD_DVSN": "00",  # 체결구분
            "ORD_GNO_BRNO": "",  # 주문채번지점번호
            "ODNO": "",  # 주문번호
            "INQR_DVSN_3": "00",  # 조회구분3
            "INQR_DVSN_1": "",  # 조회구분1
            "CTX_AREA_FK100": "",  # 연속조회검색조건100
            "CTX_AREA_NK100": "",  # 연속조회키100
        }
        
        response = await client.get(
            f"{TrIdManager.get_domain('order_list')}{ORDER_LIST_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": TrIdManager.get_tr_id("order_list")
            },
            params=request_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get order list: {response.text}")

        data = response.json()

    saved_order_history_id = None
    if save_history:
        try:
            cano = _current_account_id()
            account_type = infer_account_type(cano, acnt_prdt_cd)
            saved_order_history_id = kisdb.insert_order_history(
                cano,
                acnt_prdt_cd,
                account_type,
                "domestic",
                start_date,
                end_date,
                data,
            )
        except Exception as e:
            logger.warning(f"DB order_history save failed (non-critical): {e}")

    if return_metadata:
        return {
            "raw": data,
            "saved_order_history_id": saved_order_history_id,
        }
    return data

async def inquery_order_detail(order_no: str, order_date: str):
    """
    Get order detail from Korea Investment & Securities
    
    Args:
        order_no: Order number
        order_date: Order date (YYYYMMDD)
        
    Returns:
        Dictionary containing order detail information
    """
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")
    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        
        # Prepare request data
        request_data = {
            "CANO": os.environ["KIS_CANO"],  # 계좌번호
            "ACNT_PRDT_CD": acnt_prdt_cd,  # 계좌상품코드
            "INQR_DVSN": "00",  # 조회구분
            "PDNO": "",  # 종목코드
            "ORD_STRT_DT": order_date,  # 주문시작일자
            "ORD_END_DT": order_date,  # 주문종료일자
            "SLL_BUY_DVSN_CD": "00",  # 매도매수구분
            "CCLD_DVSN": "00",  # 체결구분
            "ORD_GNO_BRNO": "",  # 주문채번지점번호
            "ODNO": order_no,  # 주문번호
            "INQR_DVSN_3": "00",  # 조회구분3
            "INQR_DVSN_1": "",  # 조회구분1
            "CTX_AREA_FK100": "",  # 연속조회검색조건100
            "CTX_AREA_NK100": "",  # 연속조회키100
        }
        
        response = await client.get(
            f"{TrIdManager.get_domain('order_detail')}{ORDER_DETAIL_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": TrIdManager.get_tr_id("order_detail")
            },
            params=request_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get order detail: {response.text}")
        
        return response.json()

async def inquery_stock_info(symbol: str, start_date: str, end_date: str):
    """
    Get daily stock price information from Korea Investment & Securities
    
    Args:
        symbol: Stock symbol (e.g. "005930")
        start_date: Start date (YYYYMMDD)
        end_date: End date (YYYYMMDD)
        
    Returns:
        Dictionary containing daily stock price information
    """
    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        
        # Prepare request data
        request_data = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 시장구분
            "FID_INPUT_ISCD": symbol,  # 종목코드
            "FID_INPUT_DATE_1": start_date,  # 시작일자
            "FID_INPUT_DATE_2": end_date,  # 종료일자
            "FID_PERIOD_DIV_CODE": "D",  # 기간분류코드
            "FID_ORG_ADJ_PRC": "0",  # 수정주가원구분
        }
        
        response = await client.get(
            f"{TrIdManager.get_domain('stock_info')}{STOCK_INFO_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": TrIdManager.get_tr_id("stock_info")
            },
            params=request_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get stock info: {response.text}")
        
        return response.json()

async def inquery_stock_history(symbol: str, start_date: str, end_date: str):
    """
    Get daily stock price history from Korea Investment & Securities
    
    Args:
        symbol: Stock symbol (e.g. "005930")
        start_date: Start date (YYYYMMDD)
        end_date: End date (YYYYMMDD)
        
    Returns:
        Dictionary containing daily stock price history
    """
    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        
        # Prepare request data
        request_data = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 시장구분
            "FID_INPUT_ISCD": symbol,  # 종목코드
            "FID_INPUT_DATE_1": start_date,  # 시작일자
            "FID_INPUT_DATE_2": end_date,  # 종료일자
            "FID_PERIOD_DIV_CODE": "D",  # 기간분류코드
            "FID_ORG_ADJ_PRC": "0",  # 수정주가원구분
        }
        
        response = await client.get(
            f"{TrIdManager.get_domain('stock_history')}{STOCK_HISTORY_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": TrIdManager.get_tr_id("stock_history")
            },
            params=request_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get stock history: {response.text}")

        data = response.json()

        # ── DB: 주가 이력 캐시 저장 ──
        try:
            output = data.get("output2") or data.get("output", [])
            if isinstance(output, list):
                rows = []
                for item in output:
                    dt = item.get("stck_bsop_date") or item.get("stck_clpr_date")
                    if dt:
                        rows.append({
                            "symbol": symbol, "exchange": "KRX", "date": dt,
                            "open":  item.get("stck_oprc"),
                            "high":  item.get("stck_hgpr"),
                            "low":   item.get("stck_lwpr"),
                            "close": item.get("stck_clpr"),
                            "volume": item.get("acml_vol"),
                        })
                if rows:
                    kisdb.upsert_price_history(rows)
        except Exception as e:
            logger.warning(f"DB price_history save failed (non-critical): {e}")

        return data

async def inquery_stock_ask(symbol: str):
    """
    Get stock ask price from Korea Investment & Securities
    
    Args:
        symbol: Stock symbol (e.g. "005930")
        
    Returns:
        Dictionary containing stock ask price information
    """
    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        
        # Prepare request data
        request_data = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 시장구분
            "FID_INPUT_ISCD": symbol,  # 종목코드
        }
        
        response = await client.get(
            f"{TrIdManager.get_domain('stock_ask')}{STOCK_ASK_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": TrIdManager.get_tr_id("stock_ask")
            },
            params=request_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get stock ask: {response.text}")
        
        return response.json()

async def order_overseas_stock(symbol: str, quantity: int, price: float, order_type: str, market: str):
    """
    Order overseas stock (buy/sell)
    
    Args:
        symbol: Stock symbol (e.g. "AAPL")
        quantity: Order quantity
        price: Order price (0 for market price)
        order_type: Order type ("buy" or "sell", case-insensitive)
        market: Market code ("NASD" for NASDAQ, "NYSE" for NYSE, etc.)
        
    Returns:
        Dictionary containing order information
    """
    if not _order_tools_enabled():
        return _disabled_order_response()

    # Normalize order_type to lowercase
    order_type = order_type.lower()
    if order_type not in ["buy", "sell"]:
        raise ValueError('order_type must be either "buy" or "sell"')

    # Normalize market code to uppercase
    market = market.upper()
    if market not in MARKET_CODES:
        raise ValueError(f"Unsupported market: {market}. Supported markets: {', '.join(MARKET_CODES.keys())}")

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        
        # Get market prefix for TR_ID
        market_prefix = {
            "NASD": "us",  # 나스닥
            "NYSE": "us",  # 뉴욕
            "AMEX": "us",  # 아멕스
            "SEHK": "hk",  # 홍콩
            "SHAA": "sh",  # 중국상해
            "SZAA": "sz",  # 중국심천
            "TKSE": "jp",  # 일본
            "HASE": "vn",  # 베트남 하노이
            "VNSE": "vn",  # 베트남 호치민
        }.get(market)
        
        if not market_prefix:
            raise ValueError(f"Unsupported market: {market}")
            
        tr_id_key = f"{market_prefix}_{order_type}"
        tr_id = TrIdManager.get_tr_id(tr_id_key)
        
        if not tr_id:
            raise ValueError(f"Invalid operation type: {tr_id_key}")
        
        # Prepare request data
        request_data = {
            "CANO": os.environ["KIS_CANO"],           # 계좌번호
            "ACNT_PRDT_CD": "01",                     # 계좌상품코드
            "OVRS_EXCG_CD": market,                   # 해외거래소코드
            "PDNO": symbol,                           # 종목코드
            "ORD_QTY": str(quantity),                 # 주문수량
            "OVRS_ORD_UNPR": str(price),             # 주문단가
            "ORD_SVR_DVSN_CD": "0",                  # 주문서버구분코드
            "ORD_DVSN": "00" if price > 0 else "01"  # 주문구분 (00: 지정가, 01: 시장가)
        }
        
        response = await client.post(
            f"{TrIdManager.get_domain(order_type)}{OVERSEAS_ORDER_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": tr_id,
            },
            json=request_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to order overseas stock: {response.text}")
        
        return response.json()

async def inquery_overseas_stock_price(symbol: str, market: str):
    """
    Get overseas stock price
    
    Args:
        symbol: Stock symbol (e.g. "AAPL")
        market: Market code ("NASD" for NASDAQ, "NYSE" for NYSE, etc.)
        
    Returns:
        Dictionary containing stock price information
    """
    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        
        response = await client.get(
            f"{TrIdManager.get_domain('buy')}{OVERSEAS_STOCK_PRICE_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": "HHDFS00000300"
            },
            params={
                "AUTH": "",
                "EXCD": market,
                "SYMB": symbol
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get overseas stock price: {response.text}")
        
        return response.json()

async def inquery_overseas_balance(exchange: str = "ALL"):
    """
    Get overseas stock balance.

    Args:
        exchange: Exchange code to query. Use "ALL" to query all major exchanges,
                  or specify one: "NASD" (NASDAQ), "NYSE", "AMEX",
                  "SEHK" (Hong Kong), "SHAA" (Shanghai), "SZAA" (Shenzhen),
                  "TKSE" (Tokyo), "HASE" (Hanoi), "VNSE" (Ho Chi Minh).

    Returns:
        Dictionary with holdings per exchange.
    """
    # 거래소별 통화코드 매핑
    EXCHANGE_CURRENCY = {
        "NASD": "USD", "NYSE": "USD", "AMEX": "USD",
        "SEHK": "HKD",
        "SHAA": "CNY", "SZAA": "CNY",
        "TKSE": "JPY",
        "HASE": "VND", "VNSE": "VND",
    }

    if exchange == "ALL":
        targets = list(EXCHANGE_CURRENCY.items())
    else:
        if exchange not in EXCHANGE_CURRENCY:
            raise ValueError(f"Unknown exchange: {exchange}. Use ALL or one of {list(EXCHANGE_CURRENCY)}")
        targets = [(exchange, EXCHANGE_CURRENCY[exchange])]

    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")
    results = {}

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)

        for excg_cd, crcy_cd in targets:
            try:
                response = await client.get(
                    f"{DOMAIN}{OVERSEAS_BALANCE_PATH}",
                    headers={
                        "content-type": CONTENT_TYPE,
                        "authorization": f"{AUTH_TYPE} {token}",
                        "appkey": os.environ["KIS_APP_KEY"],
                        "appsecret": os.environ["KIS_APP_SECRET"],
                        "tr_id": "TTTS3012R",  # 해외주식 잔고조회 (실전)
                    },
                    params={
                        "CANO": os.environ["KIS_CANO"],
                        "ACNT_PRDT_CD": acnt_prdt_cd,
                        "OVRS_EXCG_CD": excg_cd,
                        "TR_CRCY_CD": crcy_cd,
                        "CTX_AREA_FK200": "",
                        "CTX_AREA_NK200": "",
                    },
                )
                data = response.json()
                # 잔고 있는 거래소만 포함
                output1 = data.get("output1", [])
                if output1:
                    results[excg_cd] = data
            except Exception as e:
                logger.warning(f"Failed to fetch {excg_cd} balance: {e}")

    if not results:
        return {"message": "No overseas holdings found across queried exchanges."}
    return results


async def inquery_overseas_deposit(
    wcrc_frcr_dvsn_cd: str = "02",
    natn_cd: str = "000",
):
    """
    Get overseas cash deposit (예수금) using 해외주식 체결기준현재잔고 API (CTRP6504R).

    Args:
        wcrc_frcr_dvsn_cd: "01" = 원화환산, "02" = 외화 (default: "02")
        natn_cd: 국가코드. "000"=전체, "840"=미국, "344"=홍콩, "156"=중국, "392"=일본, "704"=베트남

    Returns:
        Dict with output2 (통화별 잔고) and output3 (예수금 총계).
    """
    OVERSEAS_PRESENT_BALANCE_PATH = "/uapi/overseas-stock/v1/trading/inquire-present-balance"
    TR_ID = "CTRP6504R"

    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        response = await client.get(
            f"{DOMAIN}{OVERSEAS_PRESENT_BALANCE_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": TR_ID,
            },
            params={
                "CANO": os.environ["KIS_CANO"],
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "WCRC_FRCR_DVSN_CD": wcrc_frcr_dvsn_cd,
                "NATN_CD": natn_cd,
                "TR_MKET_CD": "00",
                "INQR_DVSN_CD": "00",
            },
        )
        data = response.json()

    # output2: 통화별 외화예수금, output3: 원화환산 총계 (예수금액, 총예수금액 등)
    result = {}
    if data.get("output2"):
        result["통화별_잔고"] = data["output2"]
    if data.get("output3"):
        o3 = data["output3"]
        result["예수금_총계"] = {
            "예수금액": o3.get("dncl_amt"),
            "총예수금액": o3.get("tot_dncl_amt"),
            "외화예수금액": o3.get("frcr_dncl_amt_2"),
            "외화사용가능금액": o3.get("frcr_use_psbl_amt"),
            "인출가능총금액": o3.get("wdrw_psbl_tot_amt"),
            "총자산금액": o3.get("tot_asst_amt"),
            "CMA평가금액": o3.get("cma_evlu_amt"),
        }
        result["적용환율"] = {
            "USD/KRW": o3.get("usd_frst_bltn_exrt"),
            "HKD/KRW": o3.get("hkd_frst_bltn_exrt"),
            "JPY/KRW": o3.get("jpy_frst_bltn_exrt"),
            "CNY/KRW": o3.get("cny_frst_bltn_exrt"),
        }
    if not result:
        result["raw"] = data
    return result


async def inquery_exchange_rate_history(
    currency: str = "USD",
    start_date: str = "",
    end_date: str = "",
    period: str = "D",
):
    """
    환율 기간별 시세 조회 (FHKST03030100).

    Args:
        currency: 통화코드. "USD"(달러), "JPY"(엔), "EUR"(유로), "CNY"(위안), "HKD"(홍콩달러)
        start_date: 시작일 YYYYMMDD (빈값이면 오늘)
        end_date:   종료일 YYYYMMDD (빈값이면 오늘)
        period: D=일, W=주, M=월, Y=년
    """
    from datetime import date
    today = date.today().strftime("%Y%m%d")
    if not start_date:
        start_date = today
    if not end_date:
        end_date = today

    # KIS 환율 종목코드 매핑 (FID_COND_MRKT_DIV_CODE=X)
    CURRENCY_ISCD = {
        "USD": "FX@KRW",
        "JPY": "FX@JPYKRW",
        "EUR": "FX@EURKRW",
        "CNY": "FX@CNYKRW",
        "HKD": "FX@HKDKRW",
        "VND": "FX@VNDKRW",
    }
    iscd = CURRENCY_ISCD.get(currency.upper(), f"FX@{currency.upper()}KRW")

    OVERSEAS_CHARTPRICE_PATH = "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice"

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        response = await client.get(
            f"{DOMAIN}{OVERSEAS_CHARTPRICE_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": "FHKST03030100",
            },
            params={
                "FID_COND_MRKT_DIV_CODE": "X",
                "FID_INPUT_ISCD": iscd,
                "FID_INPUT_DATE_1": start_date,
                "FID_INPUT_DATE_2": end_date,
                "FID_PERIOD_DIV_CODE": period,
            },
        )
    data = response.json()

    # ── DB: 환율 이력 캐시 저장 ──
    try:
        output = data.get("output2") or []
        if isinstance(output, list):
            rows = []
            for item in output:
                dt = item.get("stck_bsop_date") or item.get("xymd")
                rate = item.get("ovrs_nmix_prpr") or item.get("clos")
                if dt and rate:
                    rows.append({"date": dt, "rate": rate})
            if rows:
                kisdb.upsert_exchange_rate_history(currency, period, rows)
    except Exception as e:
        logger.warning(f"DB exchange_rate_history save failed (non-critical): {e}")

    return data


async def inquery_overseas_stock_history(
    symbol: str,
    exchange: str = "NAS",
    end_date: str = "",
    period: str = "0",
):
    """
    해외주식 기간별시세 조회 (HHDFS76240000).

    Args:
        symbol:   종목코드 (예: "AAPL", "TSLA")
        exchange: 거래소코드 NAS=나스닥, NYS=뉴욕, AMS=아멕스, HKS=홍콩, SHS=상해, SZS=심천, TSE=도쿄, HNX=하노이, HSX=호치민
        end_date: 조회기준일(YYYYMMDD). 빈값이면 오늘 기준 최근 30일
        period:   0=일, 1=주, 2=월
    """
    from datetime import date
    if not end_date:
        end_date = date.today().strftime("%Y%m%d")

    OVERSEAS_DAILYPRICE_PATH = "/uapi/overseas-price/v1/quotations/dailyprice"

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        response = await client.get(
            f"{DOMAIN}{OVERSEAS_DAILYPRICE_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": "HHDFS76240000",
            },
            params={
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": symbol,
                "GUBN": period,
                "BYMD": end_date,
                "MODP": "0",
            },
        )
    data = response.json()

    # ── DB: 해외주식 가격 이력 캐시 저장 ──
    try:
        output = data.get("output2") or []
        if isinstance(output, list):
            rows = []
            for item in output:
                dt = item.get("xymd")  # YYYYMMDD
                if dt:
                    rows.append({
                        "symbol": symbol, "exchange": exchange, "date": dt,
                        "open":   item.get("open"),
                        "high":   item.get("high"),
                        "low":    item.get("low"),
                        "close":  item.get("clos"),
                        "volume": item.get("tvol"),
                    })
            if rows:
                kisdb.upsert_price_history(rows)
    except Exception as e:
        logger.warning(f"DB overseas price_history save failed (non-critical): {e}")

    return data


async def inquery_period_trade_profit(
    start_date: str,
    end_date: str,
):
    """
    국내주식 기간별매매손익현황 조회 (TTTC8715R).

    Args:
        start_date: 조회시작일 YYYYMMDD
        end_date:   조회종료일 YYYYMMDD
    """
    PERIOD_TRADE_PROFIT_PATH = "/uapi/domestic-stock/v1/trading/inquire-period-trade-profit"
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        response = await client.get(
            f"{DOMAIN}{PERIOD_TRADE_PROFIT_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": "TTTC8715R",
            },
            params={
                "CANO": os.environ["KIS_CANO"],
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "SORT_DVSN": "00",
                "INQR_STRT_DT": start_date,
                "INQR_END_DT": end_date,
                "CBLC_DVSN": "00",
                "PDNO": "",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )
    data = response.json()
    try:
        cano = os.environ.get("KIS_CANO", "unknown")
        kisdb.insert_trade_profit(cano, "domestic", start_date, end_date, data)
    except Exception as e:
        logger.warning(f"DB trade_profit save failed (non-critical): {e}")
    return data


async def inquery_overseas_period_profit(
    start_date: str,
    end_date: str,
    exchange: str = "",
    currency: str = "",
):
    """
    해외주식 기간손익 조회 (TTTS3039R).

    Args:
        start_date: 조회시작일 YYYYMMDD
        end_date:   조회종료일 YYYYMMDD
        exchange:   거래소코드. 빈값=전체, NASD=미국, SEHK=홍콩, SHAA=중국, TKSE=일본, HASE=베트남
        currency:   통화코드. 빈값=전체, USD, HKD, CNY, JPY, VND
    """
    OVERSEAS_PERIOD_PROFIT_PATH = "/uapi/overseas-stock/v1/trading/inquire-period-profit"
    acnt_prdt_cd = os.environ.get("KIS_ACNT_PRDT_CD", "01")

    async with httpx.AsyncClient() as client:
        token = await get_access_token(client, DOMAIN)
        response = await client.get(
            f"{DOMAIN}{OVERSEAS_PERIOD_PROFIT_PATH}",
            headers={
                "content-type": CONTENT_TYPE,
                "authorization": f"{AUTH_TYPE} {token}",
                "appkey": os.environ["KIS_APP_KEY"],
                "appsecret": os.environ["KIS_APP_SECRET"],
                "tr_id": "TTTS3039R",
            },
            params={
                "CANO": os.environ["KIS_CANO"],
                "ACNT_PRDT_CD": acnt_prdt_cd,
                "OVRS_EXCG_CD": exchange,
                "NATN_CD": "",
                "CRCY_CD": currency,
                "PDNO": "",
                "INQR_STRT_DT": start_date,
                "INQR_END_DT": end_date,
                "WCRC_FRCR_DVSN_CD": "02",
                "CTX_AREA_FK200": "",
                "CTX_AREA_NK200": "",
            },
        )
    data = response.json()
    try:
        cano = os.environ.get("KIS_CANO", "unknown")
        kisdb.insert_trade_profit(cano, "overseas", start_date, end_date, data)
    except Exception as e:
        logger.warning(f"DB overseas trade_profit save failed (non-critical): {e}")
    return data


# ═══════════════════════════════════════════
# DB 조회 전용 툴 (API 호출 없음)
# ═══════════════════════════════════════════

async def get_portfolio_history(
    start_date: str = "",
    end_date: str = "",
    limit: int = 50,
):
    """
    포트폴리오 스냅샷 이력 조회 (DB only).

    Args:
        start_date: 시작일 YYYYMMDD 또는 YYYY-MM-DD (빈값=전체)
        end_date:   종료일 YYYYMMDD 또는 YYYY-MM-DD (빈값=전체)
        limit:      최대 반환 건수 (기본 50)
    """
    cano = os.environ.get("KIS_CANO", "unknown")
    rows = kisdb.get_portfolio_snapshots(cano, start_date or None, end_date or None, limit)
    return {"account_id": cano, "count": len(rows), "snapshots": rows}


async def get_token_status():
    """
    KIS 접근토큰 캐시 상태 조회.

    Returns:
        token 값 없이 발급/만료 메타데이터만 반환
    """
    return inspect_token_status()


async def get_price_from_db(
    symbol: str,
    start_date: str,
    end_date: str,
    exchange: str = "KRX",
):
    """
    캐시된 주가 이력 조회 (DB only).

    Args:
        symbol:     종목코드 (예: "005930", "AAPL")
        start_date: YYYYMMDD
        end_date:   YYYYMMDD
        exchange:   "KRX"(국내), "NAS"(나스닥), "NYSE" 등
    """
    rows = kisdb.get_price_history(symbol, exchange, start_date, end_date)
    return {"symbol": symbol, "exchange": exchange, "count": len(rows), "data": rows}


async def get_exchange_rate_from_db(
    currency: str = "USD",
    start_date: str = "",
    end_date: str = "",
    period: str = "D",
):
    """
    캐시된 환율 이력 조회 (DB only).

    Args:
        currency:   통화코드 "USD", "JPY", "CNY", "HKD", "VND"
        start_date: YYYYMMDD
        end_date:   YYYYMMDD
        period:     D=일, W=주, M=월, Y=년
    """
    from datetime import date
    if not start_date:
        start_date = "20000101"
    if not end_date:
        end_date = date.today().strftime("%Y%m%d")
    rows = kisdb.get_exchange_rate_history(currency, start_date, end_date, period)
    return {"currency": currency, "period": period, "count": len(rows), "data": rows}


async def get_bollinger_bands(
    symbol: str,
    exchange: str = "KRX",
    window: int = 20,
    num_std: float = 2.0,
    limit: int = 60,
):
    """
    볼린저 밴드 분석 (DB only).

    Args:
        symbol: 종목코드 (예: "005930", "AAPL")
        exchange: 거래소 코드. 국내는 "KRX", 해외는 "NAS", "NYS" 등 저장된 코드
        window: 이동평균 기간
        num_std: 표준편차 배수
        limit: 반환할 최근 행 수
    """
    con = kisdb.get_connection()
    return analyze_bollinger_bands(con, symbol, exchange, window, num_std, limit)


async def get_latest_portfolio_summary(
    account_id: str = "",
    lookback_days: int = 30,
):
    """
    최신 포트폴리오 합산 요약 (DB only).

    Args:
        account_id: 계좌번호. 빈값이면 DB에 저장된 모든 계좌의 최신 스냅샷을 합산
        lookback_days: 최근 스냅샷으로 인정할 기간
    """
    con = kisdb.get_connection()
    return analyze_latest_portfolio_summary(con, account_id, lookback_days)


async def get_portfolio_daily_change(
    account_id: str = "",
    days: int = 14,
):
    """
    포트폴리오 일별 변화 조회 (DB only).

    Args:
        account_id: 계좌번호. 빈값이면 DB에 저장된 모든 계좌를 일자별 합산
        days: 반환할 최근 일수
    """
    con = kisdb.get_connection()
    return analyze_portfolio_daily_change(con, account_id, days)


async def get_portfolio_anomalies(
    account_id: str = "",
    z_threshold: float = 2.0,
    lookback_days: int = 90,
    limit: int = 20,
):
    """
    포트폴리오 평가금액 이상치 탐지 (DB only).

    Args:
        account_id: 계좌번호. 빈값이면 현재 MCP 인스턴스의 KIS_CANO
        z_threshold: 이상치 기준 z-score
        lookback_days: 분석 기간
        limit: 반환할 최대 행 수
    """
    account_id = _current_account_id(account_id)
    con = kisdb.get_connection()
    return analyze_portfolio_anomalies(con, account_id, z_threshold, lookback_days, limit)


async def get_portfolio_trend(
    account_id: str = "",
    short_window: int = 7,
    long_window: int = 30,
    lookback_days: int = 90,
):
    """
    포트폴리오 추이 분석 (DB only).

    Args:
        account_id: 계좌번호. 빈값이면 현재 MCP 인스턴스의 KIS_CANO
        short_window: 단기 이동평균 일수
        long_window: 중기 이동평균 일수
        lookback_days: 조회 기간
    """
    account_id = _current_account_id(account_id)
    con = kisdb.get_connection()
    return analyze_portfolio_trend(con, account_id, short_window, long_window, lookback_days)


# Safety override: the public MCP exposes only disabled order stubs. Keep these
# names non-operative even if an internal caller imports the legacy service.
async def order_stock(symbol: str, quantity: int, price: int, order_type: str):
    return _disabled_order_response()


async def order_overseas_stock(symbol: str, quantity: int, price: float, order_type: str, market: str):
    return _disabled_order_response()
