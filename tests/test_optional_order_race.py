"""Regression coverage for competing orders of the last available copy."""
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Book, Member, Order
from app.schemas import OrderCreate
from app.services.orders import create_order

NOW = datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'orders.db'}")
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        engine.dispose()


def test_stale_stock_read_cannot_reserve_the_last_copy_twice(make_session):
    with make_session() as setup:
        member = Member(name="Member", email="member@example.com", tier="apprentice", created_at=NOW)
        book = Book(
            title="Last Copy",
            author="Author",
            isbn="9780192834010",
            price_cents=1000,
            stock=1,
            restricted=False,
        )
        setup.add_all([member, book])
        setup.commit()
        member_id, book_id = member.id, book.id

    request = OrderCreate.model_validate(
        {"member_id": member_id, "items": [{"book_id": book_id, "quantity": 1}]}
    )
    with make_session() as stale, make_session() as first:
        cached_book = stale.get(Book, book_id)
        assert cached_book.stock == 1
        assert create_order(first, request, NOW).status == "pending"

        with pytest.raises(HTTPException) as error:
            create_order(stale, request, NOW)
        assert error.value.status_code == 409

    with make_session() as check:
        assert check.get(Book, book_id).stock == 0
        assert check.scalar(select(func.count(Order.id))) == 1


def test_multi_book_order_rolls_back_earlier_reservations(make_session):
    with make_session() as setup:
        member = Member(name="Member", email="member@example.com", tier="apprentice", created_at=NOW)
        available = Book(
            title="Available",
            author="Author",
            isbn="9780192834010",
            price_cents=1000,
            stock=2,
            restricted=False,
        )
        last_copy = Book(
            title="Last Copy",
            author="Author",
            isbn="9780140449143",
            price_cents=1000,
            stock=1,
            restricted=False,
        )
        setup.add_all([member, available, last_copy])
        setup.commit()
        member_id, available_id, last_copy_id = member.id, available.id, last_copy.id

    first_request = OrderCreate.model_validate(
        {"member_id": member_id, "items": [{"book_id": last_copy_id, "quantity": 1}]}
    )
    stale_request = OrderCreate.model_validate(
        {
            "member_id": member_id,
            "items": [
                {"book_id": available_id, "quantity": 1},
                {"book_id": last_copy_id, "quantity": 1},
            ],
        }
    )

    with make_session() as stale, make_session() as first:
        cached_books = [stale.get(Book, book_id) for book_id in (available_id, last_copy_id)]
        assert [book.stock for book in cached_books] == [2, 1]
        assert create_order(first, first_request, NOW).status == "pending"

        with pytest.raises(HTTPException) as error:
            create_order(stale, stale_request, NOW)
        assert error.value.status_code == 409

    with make_session() as check:
        assert check.get(Book, available_id).stock == 2
        assert check.get(Book, last_copy_id).stock == 0
        assert check.scalar(select(func.count(Order.id))) == 1
