"""Regression coverage for stock changes made by loans and order transitions."""
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Book, Loan, Member
from app.schemas import LoanCreate
from app.services.loans import create_loan

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
