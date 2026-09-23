# Submission notes

**Live app:** https://merkle-sanctum-sanctorum.onrender.com/

**Repository:** https://github.com/Utkarshpandey0001/Merkle-Science

The app seeds demo data into an empty database at startup. In the UI, member ID `1`
is a `supreme` member and member ID `2` is a `master` member; either can access
restricted books.

## Completed work

- Implemented the book, member, order, loan, statistics, and reporting behavior in `SPEC.md`.
- Kept business rules in services and request validation in Pydantic schemas; routers
  remain thin.
- Preserved order prices when an order is placed. Order creation checks every item
  before changing stock, then saves the order and stock changes in one transaction.
- Added the optional last-copy safeguard: order creation checks and decrements stock
  in a conditional database update, and rolls back all reservations if any item runs out.
- Applied conditional database transitions to borrowing, returning, paying, and
  cancelling so stale concurrent requests cannot reserve or restore stock twice or
  overwrite a completed order status change.
- Added paginated `GET /members` and regression tests for stale stock reads,
  multi-book rollback, and member list page boundaries.
- Used the injected clock for order, member, and loan timestamps and overdue checks.
- All 216 local tests pass with the default SQLite test setup.

## Deployment and trade-offs

The local app uses SQLite, while the public deployment uses Neon Postgres and a
single Render web service that serves both the API and frontend. The only added
package is an optional PostgreSQL driver installed by Render; local tests retain
their default dependency set. The database URL is stored in Render's environment
settings and is not committed.

`Base.metadata.create_all()` creates tables for a new database but does not migrate
existing tables. My existing local `sanctum.db` predates the new loan columns, and I
left that file untouched. Loan actions against that old local file need a schema
migration or a fresh database; the tests use fresh databases, and Neon starts fresh.

If extending the app, I would add schema migrations rather than relying on table
creation alone when the data model changes.

## Specification questions

I did not need to change the acceptance tests. The spec intentionally leaves
mixed-case title sorting unspecified across SQLite and Postgres.

## AI usage

I used Codex to understand parts of the specification and discuss implementation
choices. I broke the work into small tasks and wrote the code for the first six
commits myself. After that, I asked Codex to follow the same style: make one
focused change at a time and create a separate commit for each logical fix. I
reviewed its changes and ran the test suite as we progressed. Keeping changes
small made them easier for me to understand and check.

Early on, Codex made an unwanted edit to the ISBN validation code before I had
asked it to implement that part. I caught it, stopped the change, and worked
through the checksum logic myself. That experience made me more explicit about
when I wanted an explanation, a review, or an actual code change.
