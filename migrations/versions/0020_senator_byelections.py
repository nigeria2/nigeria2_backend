"""update senators for post-2023 by-elections / defections

Anambra South: Ifeanyi Ubah (YPP, died 2024) -> Emmanuel Nwachukwu (APGA)
Yobe East:     Ibrahim Gaidam (-> Minister) -> Musa Mustapha (APC)
Kano Central:  Rufai Hanga NNPP -> NDC (defection, same seat)

Displaced senators are kept as (past) politicians with an updated title.

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_or_create_politician(conn, name: str, state: str, title: str, party: str) -> int:
    pid = conn.execute(
        sa.text("SELECT id FROM politicians WHERE name = :n AND state = :s ORDER BY id LIMIT 1"),
        {"n": name, "s": state},
    ).scalar()
    if pid:
        return pid
    conn.execute(
        sa.text("INSERT INTO politicians (name, state, title, party, note, photo) VALUES (:n, :s, :t, :p, '', '')"),
        {"n": name, "s": state, "t": title, "p": party},
    )
    return conn.execute(
        sa.text("SELECT id FROM politicians WHERE name = :n AND state = :s ORDER BY id DESC LIMIT 1"),
        {"n": name, "s": state},
    ).scalar()


def upgrade() -> None:
    conn = op.get_bind()

    # On a fresh database the senators table is still empty at migration time and
    # the (already-corrected) seed data loads the current occupants directly, so
    # there is nothing to convert. Only touch already-seeded (live) databases.
    if not conn.execute(sa.text("SELECT COUNT(*) FROM senators")).scalar():
        return

    # --- Anambra South: Ifeanyi Ubah (deceased) -> Emmanuel Nwachukwu (APGA) ---
    conn.execute(
        sa.text("UPDATE politicians SET title = :t WHERE name = 'Ifeanyi Ubah' AND state = 'Anambra'"),
        {"t": "Former Senator, Anambra South (deceased 2024)"},
    )
    pid = _get_or_create_politician(conn, "Emmanuel Nwachukwu", "Anambra", "Senator, Anambra South", "APGA")
    conn.execute(
        sa.text("UPDATE senators SET name = :n, party = 'APGA', gender = 'Male', age = NULL, terms = 1, politician_id = :pid WHERE state = 'Anambra' AND district = 'South'"),
        {"n": "Emmanuel Nwachukwu", "pid": pid},
    )

    # --- Yobe East: Ibrahim Gaidam (now minister) -> Musa Mustapha (APC) ---
    conn.execute(
        sa.text("UPDATE politicians SET title = :t WHERE name = 'Ibrahim Gaidam' AND state = 'Yobe'"),
        {"t": "Minister of Police Affairs; former Senator, Yobe East"},
    )
    pid2 = _get_or_create_politician(conn, "Musa Mustapha", "Yobe", "Senator, Yobe East", "APC")
    conn.execute(
        sa.text("UPDATE senators SET name = :n, party = 'APC', gender = 'Male', age = NULL, terms = 1, politician_id = :pid WHERE state = 'Yobe' AND district = 'East'"),
        {"n": "Musa Mustapha", "pid": pid2},
    )

    # --- Kano Central: Rufai Hanga defected NNPP -> NDC (same seat) ---
    conn.execute(sa.text("UPDATE senators SET party = 'NDC' WHERE state = 'Kano' AND district = 'Central'"))
    conn.execute(sa.text("UPDATE politicians SET party = 'NDC' WHERE name = 'Rufai Hanga' AND state = 'Kano'"))


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("UPDATE senators SET party = 'NNPP' WHERE state = 'Kano' AND district = 'Central'"))
    conn.execute(sa.text("UPDATE politicians SET party = 'NNPP' WHERE name = 'Rufai Hanga' AND state = 'Kano'"))

    ubah = conn.execute(sa.text("SELECT id FROM politicians WHERE name = 'Ifeanyi Ubah' AND state = 'Anambra' ORDER BY id LIMIT 1")).scalar()
    conn.execute(
        sa.text("UPDATE senators SET name = 'Ifeanyi Ubah', party = 'YPP', gender = '', age = NULL, terms = NULL, politician_id = :pid WHERE state = 'Anambra' AND district = 'South'"),
        {"pid": ubah},
    )
    conn.execute(sa.text("UPDATE politicians SET title = 'Senator, Anambra South' WHERE name = 'Ifeanyi Ubah' AND state = 'Anambra'"))
    conn.execute(sa.text("DELETE FROM politicians WHERE name = 'Emmanuel Nwachukwu' AND state = 'Anambra'"))

    gaidam = conn.execute(sa.text("SELECT id FROM politicians WHERE name = 'Ibrahim Gaidam' AND state = 'Yobe' ORDER BY id LIMIT 1")).scalar()
    conn.execute(
        sa.text("UPDATE senators SET name = 'Ibrahim Gaidam', party = 'APC', gender = 'Male', age = 70, terms = 2, politician_id = :pid WHERE state = 'Yobe' AND district = 'East'"),
        {"pid": gaidam},
    )
    conn.execute(sa.text("UPDATE politicians SET title = 'Senator, Yobe East' WHERE name = 'Ibrahim Gaidam' AND state = 'Yobe'"))
    conn.execute(sa.text("DELETE FROM politicians WHERE name = 'Musa Mustapha' AND state = 'Yobe'"))
