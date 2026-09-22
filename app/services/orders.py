"""Order operations: placing, paying and cancelling purchases."""
from datetime import datetime
from typing import Dict

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import Book, Member, MemberTier, Order, OrderItem, OrderStatus
from app.schemas import OrderCreate
from app.services.members import ensure_can_access_restricted, get_member

# Percentage discount granted by each membership tier.
TIER_DISCOUNT_PERCENT: Dict[str, int] = {
    MemberTier.APPRENTICE.value: 0,
    MemberTier.ADEPT.value: 5,
    MemberTier.MASTER.value: 10,
    MemberTier.SUPREME.value: 15,
}

# Extra discount when the total quantity across all items reaches the threshold.
BULK_QUANTITY_THRESHOLD = 10
BULK_DISCOUNT_PERCENT = 5


def calculate_discount_percent(member: Member, total_quantity: int) -> int:
    """Tier discount, plus the bulk discount when total quantity >= threshold."""
    percent = TIER_DISCOUNT_PERCENT[member.tier]
    if total_quantity >= BULK_QUANTITY_THRESHOLD:
        percent += BULK_DISCOUNT_PERCENT
    return percent


def create_order(db: Session, data: OrderCreate, now: datetime) -> Order:
    """Place a pending order and reserve stock.

    Checks, in order (422 for empty items / bad quantity / duplicate books is done by the schema):
    1. 404 member not found; 404 any book not found
    2. 403 any book restricted and member tier below master
    3. 409 any book has insufficient stock (all-or-nothing: nothing is changed)
    Then stock is decremented for every item and prices are snapshotted.
    Pricing: discount_cents = subtotal * percent // 100; total = subtotal - discount.
    """
    member = get_member(db, data.member_id)
    books = []
    for item in data.items:
        book = db.get(Book, item.book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="Book not found")
        books.append(book)

    for book in books:
        if book.restricted:
            ensure_can_access_restricted(member)

    for item, book in zip(data.items, books):
        if book.stock < item.quantity:
            raise HTTPException(status_code=409, detail="Insufficient stock")

    # A book's stock may have changed since it was read above. Each update checks
    # the current database value while reserving stock. Keep a consistent lock
    # order across multi-book orders, and roll back earlier updates on failure.
    for item in sorted(data.items, key=lambda item: item.book_id):
        result = db.execute(
            update(Book)
            .where(Book.id == item.book_id, Book.stock >= item.quantity)
            .values(stock=Book.stock - item.quantity)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="Insufficient stock")

    order_items = [
        OrderItem(book_id=book.id, quantity=item.quantity, unit_price_cents=book.price_cents)
        for item, book in zip(data.items, books)
    ]

    subtotal_cents = sum(item.line_total_cents for item in order_items)
    discount_percent = calculate_discount_percent(member, sum(item.quantity for item in data.items))
    discount_cents = subtotal_cents * discount_percent // 100
    order = Order(
        member_id=member.id,
        status=OrderStatus.PENDING.value,
        items=order_items,
        subtotal_cents=subtotal_cents,
        discount_percent=discount_percent,
        discount_cents=discount_cents,
        total_cents=subtotal_cents - discount_cents,
        created_at=now,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_order(db: Session, order_id: int) -> Order:
    """Return an order by id, or raise 404."""
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def pay_order(db: Session, order_id: int) -> Order:
    """Mark a pending order as paid. 404 if missing; 409 if not pending."""
    order = get_order(db, order_id)
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Cannot pay an order that is {order.status}")
    order.status = OrderStatus.PAID.value
    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, order_id: int) -> Order:
    """Cancel a pending order and restore the reserved stock. 404 if missing; 409 if not pending."""
    order = get_order(db, order_id)
    if order.status != OrderStatus.PENDING.value:
        raise HTTPException(status_code=409, detail=f"Cannot cancel an order that is {order.status}")
    for item in order.items:
        item.book.stock += item.quantity
    order.status = OrderStatus.CANCELLED.value
    db.commit()
    db.refresh(order)
    return order
