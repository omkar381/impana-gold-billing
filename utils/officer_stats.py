"""
utils/officer_stats.py — Sales numbers and motivation for the officer app.

Everything is derived from confirmed bills attributed to the officer, so
nothing can be "earned" until the superadmin has approved the order and a real
bill exists. Nothing here is stored; it is recalculated on each request.
"""

import calendar
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import and_, func, or_

from extensions import db
from models import Bill, Customer, MarketingOfficer
from utils.timeutil import now_ist, today_ist

QUOTES = [
    "Every big order started as a small conversation.",
    "Consistency beats intensity. Show up at one more shop today.",
    "A happy shopkeeper reorders. Be the reason.",
    "Your target is just a number of good conversations away.",
    "Quality sells itself, but only after you walk in the door.",
    "Today's visit is next month's regular customer.",
    "Small wins stack up. Close the next one.",
    "People buy from people they trust. Be on time, be honest.",
    "Don't count the days. Make the days count.",
    "The best time to ask for the order is right after you help.",
]

LEVELS = [  # (minimum % of target, title)
    (100, "Champion"),
    (75, "Star Performer"),
    (50, "Pro Seller"),
    (25, "Rising Seller"),
    (0, "Getting Started"),
]


def attributed(officer):
    """SQL filter for confirmed bills credited to this officer."""
    return and_(
        Bill.status == "confirmed",
        or_(
            Bill.marketing_officer_id == officer.id,
            and_(Bill.marketing_officer_id.is_(None), Bill.marketing_officer_name == officer.name),
        ),
    )


def month_bounds(day=None):
    day = day or today_ist()
    last = calendar.monthrange(day.year, day.month)[1]
    return day.replace(day=1), day.replace(day=last)


def _day_start(d):
    return datetime.combine(d, datetime.min.time())


def _day_end(d):
    return datetime.combine(d, datetime.max.time())


def sales_between(officer, start, end):
    """(order_count, total) for confirmed bills between two dates inclusive."""
    row = (
        db.session.query(func.count(Bill.id), func.coalesce(func.sum(Bill.grand_total), 0))
        .filter(attributed(officer), Bill.bill_date >= _day_start(start), Bill.bill_date <= _day_end(end))
        .one()
    )
    return int(row[0] or 0), Decimal(str(row[1] or 0))


def streak_days(officer):
    """Consecutive days (ending today, or yesterday if nothing yet today) with a sale."""
    since = today_ist() - timedelta(days=90)
    rows = (
        db.session.query(func.date(Bill.bill_date))
        .filter(attributed(officer), Bill.bill_date >= _day_start(since))
        .distinct()
        .all()
    )
    days = {str(r[0])[:10] for r in rows}
    cursor = today_ist()
    if cursor.isoformat() not in days:
        cursor -= timedelta(days=1)
    count = 0
    while cursor.isoformat() in days:
        count += 1
        cursor -= timedelta(days=1)
    return count


def level_for(pct):
    for minimum, title in LEVELS:
        if pct >= minimum:
            return title
    return LEVELS[-1][1]


def points(total):
    """Friendly score: 1 point per ₹100 of approved sales this month."""
    return int(Decimal(str(total or 0)) // 100)


def leaderboard():
    """Active officers ranked by this month's approved sales (points only, no amounts shown)."""
    start, end = month_bounds()
    rows = []
    for o in MarketingOfficer.query.filter_by(is_active=True).all():
        _, total = sales_between(o, start, end)
        rows.append({"id": o.id, "name": o.name, "photo": o.photo_path, "points": points(total), "total": total})
    rows.sort(key=lambda r: (-r["total"], r["name"].lower()))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def overview(officer):
    """All numbers the home screen needs."""
    today = today_ist()
    m_start, m_end = month_bounds(today)

    today_orders, today_total = sales_between(officer, today, today)
    month_orders, month_total = sales_between(officer, m_start, m_end)

    target = Decimal(str(officer.monthly_target or 0))
    pct = int(month_total / target * 100) if target > 0 else 0
    remaining = max(target - month_total, Decimal("0"))

    lifetime = db.session.query(func.count(Bill.id)).filter(attributed(officer)).scalar() or 0
    biggest = float(db.session.query(func.coalesce(func.max(Bill.grand_total), 0)).filter(attributed(officer)).scalar() or 0)
    streak = streak_days(officer)
    mt = float(month_total)

    badge_list = [
        {"title": "First Sale", "hint": "Get your first order approved", "earned": lifetime >= 1},
        {"title": "10 Orders", "hint": "Reach 10 approved orders", "earned": lifetime >= 10},
        {"title": "Big Deal", "hint": "One order of ₹25,000 or more", "earned": biggest >= 25000},
        {"title": "5-Day Streak", "hint": "Sell 5 days in a row", "earned": streak >= 5},
        {"title": "₹50K Month", "hint": "₹50,000 in a month", "earned": mt >= 50000},
        {"title": "Target Hit", "hint": "Reach your monthly target", "earned": bool(target > 0 and month_total >= target)},
    ]

    board = leaderboard()
    mine = next((r for r in board if r["id"] == officer.id), None)

    hour = now_ist().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

    if target > 0:
        level = level_for(pct)
    else:
        level = "Rising Seller" if month_orders else "Getting Started"

    return {
        "today_orders": today_orders,
        "today_total": today_total,
        "month_orders": month_orders,
        "month_total": month_total,
        "target": target,
        "pct": pct,
        "ring_pct": min(pct, 100),
        "remaining": remaining,
        "days_left": (m_end - today).days,
        "level": level,
        "streak": streak,
        "badges": badge_list,
        "earned_count": sum(1 for b in badge_list if b["earned"]),
        "leaderboard": board[:5],
        "my_rank": mine["rank"] if mine else None,
        "my_points": mine["points"] if mine else 0,
        "officers_count": len(board),
        "greeting": greeting,
        "quote": QUOTES[today.toordinal() % len(QUOTES)],
    }


def shops_for(officer):
    """Shops this officer has sold to (never the full customer list)."""
    rows = (
        db.session.query(
            Customer.id,
            Customer.name,
            Customer.phone,
            func.count(Bill.id),
            func.coalesce(func.sum(Bill.grand_total), 0),
            func.max(Bill.bill_date),
        )
        .join(Bill, Bill.customer_id == Customer.id)
        .filter(attributed(officer), Customer.deleted_at.is_(None))
        .group_by(Customer.id, Customer.name, Customer.phone)
        .order_by(func.max(Bill.bill_date).desc())
        .all()
    )
    return [
        {"id": r[0], "name": r[1], "phone": r[2], "orders": int(r[3]), "total": Decimal(str(r[4])), "last": r[5]}
        for r in rows
    ]
