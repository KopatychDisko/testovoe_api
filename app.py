import asyncio
import logging
import re
from datetime import datetime

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

ORDERS_URL: str = "https://test.ooobs.ru/api/orders"
FETCH_ATTEMPTS: int = 3
FETCH_TIMEOUT_SECONDS: float = 10.0
RETRY_DELAY_SECONDS: float = 0.5

logger: logging.Logger = logging.getLogger("orders-sync")


class Order(BaseModel):
    id: int
    name: str
    phone: str
    email: str
    amount: int | float
    created_at: datetime


class Client(BaseModel):
    name: str
    phone: str
    email: str
    amount: int | float


class Stats(BaseModel):
    received: int
    unique: int
    duplicates_merged: int
    invalid_dropped: int


class SyncResult(BaseModel):
    clients: list[Client]
    stats: Stats


def normalize_phone(raw: str) -> str | None:
    """Return phone as +7XXXXXXXXXX, or None if it cannot be reduced to 11 digits."""
    digits: str = re.sub(r"[^0-9]", "", raw)
    # A 10-digit number starting with 7/8 is a truncated number with a country code, not a local one
    if len(digits) == 10 and digits[0] not in ("7", "8"):
        return f"+7{digits}"
    if len(digits) == 11 and digits[0] in ("7", "8"):
        return f"+7{digits[1:]}"
    return None


def is_better(candidate: Order, current: Order) -> bool:
    """Higher amount wins; on equal amounts the later created_at wins."""
    return (candidate.amount, candidate.created_at) > (current.amount, current.created_at)


def sync_orders(orders: list[Order]) -> SyncResult:
    best_by_phone: dict[str, Order] = {}
    invalid_dropped: int = 0
    for order in orders:
        phone: str | None = normalize_phone(order.phone)
        if phone is None:
            invalid_dropped += 1
            continue
        current: Order | None = best_by_phone.get(phone)
        if current is None or is_better(order, current):
            best_by_phone[phone] = order
    clients: list[Client] = [
        Client(name=o.name, phone=phone, email=o.email, amount=o.amount)
        for phone, o in best_by_phone.items()
    ]
    valid_count: int = len(orders) - invalid_dropped
    return SyncResult(
        clients=clients,
        stats=Stats(
            received=len(orders),
            unique=len(clients),
            duplicates_merged=valid_count - len(clients),
            invalid_dropped=invalid_dropped,
        ),
    )


async def fetch_orders() -> list[Order]:
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
        for attempt in range(1, FETCH_ATTEMPTS + 1):
            try:
                response: httpx.Response = await client.get(ORDERS_URL)
                response.raise_for_status()
                return [Order.model_validate(item) for item in response.json()]
            except (httpx.HTTPError, ValueError) as error:
                last_error = error
                logger.warning(
                    "Fetching orders failed",
                    extra={"attempt": attempt, "url": ORDERS_URL, "error": repr(error)},
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(
        f"Failed to fetch orders from {ORDERS_URL} after {FETCH_ATTEMPTS} attempts: {last_error!r}"
    )


app: FastAPI = FastAPI()


@app.get("/")
@app.get("/clients")
async def get_clients() -> JSONResponse:
    try:
        orders: list[Order] = await fetch_orders()
    except RuntimeError as error:
        return JSONResponse(status_code=502, content={"error": str(error)})
    return JSONResponse(content=sync_orders(orders).model_dump(mode="json"))
