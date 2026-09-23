"""Regression coverage for stock changes made by loans and order transitions."""
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Book, Loan, Member, Order
from app.schemas import LoanCreate, OrderCreate
from app.services.loans import create_loan, return_loan
from app.services.orders import cancel_order, create_order, pay_order

NOW = datetime(2026, 1, 1, 12, 0, 0)


@pytest.fixture
def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stock-transitions.db'}")
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        engine.dispose()


def test_stale_loan_request_cannot_borrow_the_last_copy(make_session):
    with make_session() as setup:
        first_member = Member(
            name="First Member", email="first@example.com", tier="apprentice", created_at=NOW
        )
        second_member = Member(
            name="Second Member", email="second@example.com", tier="apprentice", created_at=NOW
        )
        book = Book(
            title="Last Copy",
            author="Author",
            isbn="9780192834010",
            price_cents=1000,
            stock=1,
            restricted=False,
        )
        setup.add_all([first_member, second_member, book])
        setup.commit()
        first_member_id, second_member_id, book_id = first_member.id, second_member.id, book.id

    first_request = LoanCreate(member_id=first_member_id, book_id=book_id)
    stale_request = LoanCreate(member_id=second_member_id, book_id=book_id)
    with make_session() as stale, make_session() as first:
        cached_book = stale.get(Book, book_id)
        assert cached_book.stock == 1
        assert create_loan(first, first_request, NOW).status == "active"

        with pytest.raises(HTTPException) as error:
            create_loan(stale, stale_request, NOW)
        assert error.value.status_code == 409

    with make_session() as check:
        assert check.get(Book, book_id).stock == 0
        assert check.scalar(select(func.count(Loan.id))) == 1


def test_stale_return_request_restores_stock_only_once(make_session):
    with make_session() as setup:
        member = Member(
            name="Member", email="member@example.com", tier="apprentice", created_at=NOW
        )
        book = Book(
            title="Borrowed Book",
            author="Author",
            isbn="9780192834010",
            price_cents=1000,
            stock=1,
            restricted=False,
        )
        setup.add_all([member, book])
        setup.commit()
        loan = create_loan(setup, LoanCreate(member_id=member.id, book_id=book.id), NOW)
        loan_id, book_id = loan.id, book.id

    with make_session() as stale, make_session() as first:
        cached_loan = stale.get(Loan, loan_id)
        assert cached_loan.returned_at is None
        assert stale.get(Book, book_id).stock == 0
        assert return_loan(first, loan_id, NOW).status == "returned"

        with pytest.raises(HTTPException) as error:
            return_loan(stale, loan_id, NOW)
        assert error.value.status_code == 409

    with make_session() as check:
        assert check.get(Book, book_id).stock == 1
        assert check.get(Loan, loan_id).returned_at == NOW


def test_stale_cancellation_restores_order_stock_only_once(make_session):
    with make_session() as setup:
        member = Member(
            name="Member", email="member@example.com", tier="apprentice", created_at=NOW
        )
        book = Book(
            title="Ordered Book",
            author="Author",
            isbn="9780192834010",
            price_cents=1000,
            stock=5,
            restricted=False,
        )
        setup.add_all([member, book])
        setup.commit()
        order = create_order(
            setup,
            OrderCreate.model_validate(
                {"member_id": member.id, "items": [{"book_id": book.id, "quantity": 3}]}
            ),
            NOW,
        )
        order_id, book_id = order.id, book.id

    with make_session() as stale, make_session() as first:
        cached_order = stale.get(Order, order_id)
        assert cached_order.status == "pending"
        assert len(cached_order.items) == 1
        assert stale.get(Book, book_id).stock == 2
        assert cancel_order(first, order_id).status == "cancelled"

        with pytest.raises(HTTPException) as error:
            cancel_order(stale, order_id)
        assert error.value.status_code == 409

    with make_session() as check:
        assert check.get(Book, book_id).stock == 5
        assert check.get(Order, order_id).status == "cancelled"


def test_stale_payment_cannot_overwrite_a_cancellation(make_session):
    with make_session() as setup:
        member = Member(
            name="Member", email="member@example.com", tier="apprentice", created_at=NOW
        )
        book = Book(
            title="Ordered Book",
            author="Author",
            isbn="9780192834010",
            price_cents=1000,
            stock=2,
            restricted=False,
        )
        setup.add_all([member, book])
        setup.commit()
        order = create_order(
            setup,
            OrderCreate.model_validate(
                {"member_id": member.id, "items": [{"book_id": book.id, "quantity": 1}]}
            ),
            NOW,
        )
        order_id, book_id = order.id, book.id

    with make_session() as stale_payment, make_session() as cancellation:
        cached_order = stale_payment.get(Order, order_id)
        assert cached_order.status == "pending"
        assert cancel_order(cancellation, order_id).status == "cancelled"

        with pytest.raises(HTTPException) as error:
            pay_order(stale_payment, order_id)
        assert error.value.status_code == 409

    with make_session() as check:
        assert check.get(Book, book_id).stock == 2
        assert check.get(Order, order_id).status == "cancelled"
