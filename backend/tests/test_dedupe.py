"""
Transaction de-duplication.

Re-uploading an overlapping statement is normal user behaviour. Before this,
every re-upload doubled their spending and silently corrupted the twin.
"""
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app import models
from app.services import dedupe


class TestHashing:
    def test_identical_rows_hash_the_same(self):
        a = dedupe.transaction_hash("2026-03-01", -1500.0, "Swiggy", "Food order")
        b = dedupe.transaction_hash("2026-03-01", -1500.0, "Swiggy", "Food order")
        assert a == b

    def test_datetime_and_string_dates_agree(self):
        a = dedupe.transaction_hash(datetime(2026, 3, 1, 14, 30), -1500.0, "Swiggy")
        b = dedupe.transaction_hash("2026-03-01", -1500.0, "Swiggy")
        assert a == b, "time-of-day must not change a transaction's identity"

    def test_different_amount_hashes_differently(self):
        a = dedupe.transaction_hash("2026-03-01", -1500.0, "Swiggy")
        b = dedupe.transaction_hash("2026-03-01", -1501.0, "Swiggy")
        assert a != b

    def test_different_date_hashes_differently(self):
        a = dedupe.transaction_hash("2026-03-01", -1500.0, "Swiggy")
        b = dedupe.transaction_hash("2026-03-02", -1500.0, "Swiggy")
        assert a != b

    def test_reference_noise_is_ignored(self):
        """The same charge exported twice carries different reference numbers."""
        a = dedupe.transaction_hash("2026-03-01", -1500.0, "SWIGGY", "UPI Ref: 123456789012")
        b = dedupe.transaction_hash("2026-03-01", -1500.0, "swiggy", "UPI Ref: 987654321098")
        assert a == b

    def test_case_and_punctuation_are_normalised(self):
        a = dedupe.transaction_hash("2026-03-01", -100.0, "Amazon.in")
        b = dedupe.transaction_hash("2026-03-01", -100.0, "AMAZON IN")
        assert a == b

    def test_distinct_merchants_stay_distinct(self):
        a = dedupe.transaction_hash("2026-03-01", -100.0, "Swiggy")
        b = dedupe.transaction_hash("2026-03-01", -100.0, "Zomato")
        assert a != b


class TestPartitionNew:
    def _rows(self):
        return [
            {"date": "2026-03-01", "amount": -1500.0, "merchant": "Swiggy", "note": "food"},
            {"date": "2026-03-02", "amount": -300.0, "merchant": "Uber", "note": "ride"},
        ]

    def test_all_new_on_first_import(self, db, user):
        new, dupes = dedupe.partition_new(db, user.id, self._rows())
        assert len(new) == 2 and len(dupes) == 0
        assert all(r["dedupe_hash"] for r in new)

    def test_second_import_of_same_file_is_all_duplicates(self, db, user):
        new, _ = dedupe.partition_new(db, user.id, self._rows())
        for row in new:
            db.add(models.Transaction(
                user_id=user.id, date=datetime.fromisoformat(row["date"]),
                amount=row["amount"], category="Other", type="expense",
                merchant=row["merchant"], note=row["note"],
                dedupe_hash=row["dedupe_hash"],
            ))
        db.commit()

        new2, dupes2 = dedupe.partition_new(db, user.id, self._rows())
        assert new2 == []
        assert len(dupes2) == 2

    def test_overlapping_import_keeps_only_the_new_rows(self, db, user):
        new, _ = dedupe.partition_new(db, user.id, self._rows())
        for row in new:
            db.add(models.Transaction(
                user_id=user.id, date=datetime.fromisoformat(row["date"]),
                amount=row["amount"], category="Other", type="expense",
                merchant=row["merchant"], note=row["note"],
                dedupe_hash=row["dedupe_hash"],
            ))
        db.commit()

        overlapping = self._rows() + [
            {"date": "2026-03-03", "amount": -900.0, "merchant": "BigBasket", "note": "groceries"}
        ]
        new2, dupes2 = dedupe.partition_new(db, user.id, overlapping)
        assert len(new2) == 1
        assert new2[0]["merchant"] == "BigBasket"
        assert len(dupes2) == 2

    def test_genuine_same_day_repeats_are_kept(self, db, user):
        """
        Two identical Rs 200 coffees on the same day are two real purchases.
        Collapsing them would under-report the user's spending.
        """
        rows = self._rows() + [dict(self._rows()[0])]
        new, dupes = dedupe.partition_new(db, user.id, rows)
        assert len(new) == 3, "a legitimate repeat must not be dropped"
        assert len(dupes) == 0
        assert len({r["dedupe_hash"] for r in new}) == 3, "hashes must be distinct"

    def test_reimport_of_a_file_containing_repeats_is_a_no_op(self, db, user):
        """The occurrence index has to be stable across imports of the same file."""
        rows = self._rows() + [dict(self._rows()[0])]
        new, _ = dedupe.partition_new(db, user.id, rows)
        for row in new:
            db.add(models.Transaction(
                user_id=user.id, date=datetime.fromisoformat(row["date"]),
                amount=row["amount"], category="Other", type="expense",
                merchant=row["merchant"], note=row["note"],
                dedupe_hash=row["dedupe_hash"],
            ))
        db.commit()

        new2, dupes2 = dedupe.partition_new(db, user.id, rows)
        assert new2 == []
        assert len(dupes2) == 3

    def test_extra_repeat_in_a_later_import_is_new(self, db, user):
        """DB has 2 identical rows; a file with 3 contributes exactly 1 more."""
        rows = self._rows() + [dict(self._rows()[0])]
        new, _ = dedupe.partition_new(db, user.id, rows)
        for row in new:
            db.add(models.Transaction(
                user_id=user.id, date=datetime.fromisoformat(row["date"]),
                amount=row["amount"], category="Other", type="expense",
                merchant=row["merchant"], note=row["note"],
                dedupe_hash=row["dedupe_hash"],
            ))
        db.commit()

        more = rows + [dict(self._rows()[0])]
        new2, dupes2 = dedupe.partition_new(db, user.id, more)
        assert len(new2) == 1
        assert len(dupes2) == 3

    def test_users_do_not_share_dedup_state(self, db, user):
        other = models.User(name="Other", email="other-dedupe@finmate.test")
        db.add(other)
        db.commit()
        db.refresh(other)

        new, _ = dedupe.partition_new(db, user.id, self._rows())
        for row in new:
            db.add(models.Transaction(
                user_id=user.id, date=datetime.fromisoformat(row["date"]),
                amount=row["amount"], category="Other", type="expense",
                merchant=row["merchant"], note=row["note"],
                dedupe_hash=row["dedupe_hash"],
            ))
        db.commit()

        # The same statement uploaded by a different user is entirely new.
        new2, dupes2 = dedupe.partition_new(db, other.id, self._rows())
        assert len(new2) == 2 and len(dupes2) == 0


def test_unique_constraint_is_enforced_at_the_database(db, user):
    """Application-level dedup is not the only guard - the schema backs it."""
    h = dedupe.transaction_hash("2026-03-01", -100.0, "Swiggy")
    db.add(models.Transaction(user_id=user.id, date=datetime(2026, 3, 1), amount=-100.0,
                              category="Food", type="expense", dedupe_hash=h))
    db.commit()

    db.add(models.Transaction(user_id=user.id, date=datetime(2026, 3, 1), amount=-100.0,
                              category="Food", type="expense", dedupe_hash=h))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_backfill_populates_legacy_rows(db, user):
    """Rows imported before dedup existed get a hash so re-uploads are caught."""
    db.add_all([
        models.Transaction(user_id=user.id, date=datetime(2026, 1, 5), amount=-250.0,
                           category="Food", type="expense", merchant="Zomato"),
        models.Transaction(user_id=user.id, date=datetime(2026, 1, 6), amount=-450.0,
                           category="Transport", type="expense", merchant="Ola"),
    ])
    db.commit()

    updated = dedupe.backfill_hashes(db)
    assert updated == 2

    rows = db.query(models.Transaction).filter(models.Transaction.user_id == user.id).all()
    assert all(r.dedupe_hash for r in rows)
