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
- Used the injected clock for order, member, and loan timestamps and overdue checks.
- The complete local test suite passes with the default in-memory SQLite test setup.

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

The optional concurrent-order safeguard for the last book copy and optional
paginated `GET /members` endpoint were not implemented. If extending the app, I
would add migrations and database-level concurrency control before relying on it
for production stock management.

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
