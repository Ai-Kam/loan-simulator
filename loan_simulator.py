# Copyright (c) 2026 Aihisa Kamijo. All rights reserved.
from __future__ import annotations

import argparse
import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path


COPYRIGHT_NOTICE = "Copyright (c) 2026 Aihisa Kamijo. All rights reserved."


@dataclass(frozen=True)
class PaymentRow:
    month: int
    year: int
    annual_rate: float
    payment: float
    scheduled_payment: float
    interest: float
    unpaid_generated: float
    paid_unpaid_interest: float
    principal: float
    balance: float
    unpaid_interest: float
    total_debt: float


def monthly_payment(balance: float, annual_rate: float, remaining_months: int) -> float:
    """Return the constant monthly payment for the current rate period."""
    if remaining_months <= 0:
        raise ValueError("remaining_months must be positive")

    monthly_rate = annual_rate / 100 / 12
    if abs(monthly_rate) < 1e-12:
        return balance / remaining_months

    return balance * monthly_rate / (1 - (1 + monthly_rate) ** (-remaining_months))


def rate_for_year(annual_rates: list[float], year: int) -> float:
    if not annual_rates:
        raise ValueError("annual_rates must contain at least one rate")
    return annual_rates[min(year - 1, len(annual_rates) - 1)]


def simulate_loan(
    principal: float,
    term_years: int,
    annual_rates: list[float],
) -> list[PaymentRow]:
    if principal <= 0:
        raise ValueError("principal must be positive")
    if term_years <= 0:
        raise ValueError("term_years must be positive")

    total_months = term_years * 12
    balance = float(principal)
    unpaid_interest = 0.0
    payment = 0.0
    rows: list[PaymentRow] = []

    for month in range(1, total_months + 1):
        year = (month - 1) // 12 + 1
        annual_rate = rate_for_year(annual_rates, year)
        remaining_months = total_months - month + 1

        if month == 1 or (month - 1) % 60 == 0:
            recalculated_payment = monthly_payment(balance + unpaid_interest, annual_rate, remaining_months)
            payment = recalculated_payment if month == 1 else min(recalculated_payment, payment * 1.25)

        monthly_rate = annual_rate / 100 / 12
        interest = balance * monthly_rate
        available_payment = payment
        paid_current_interest = min(available_payment, interest)
        unpaid_generated = max(0.0, interest - paid_current_interest)
        available_payment -= paid_current_interest
        unpaid_interest += unpaid_generated

        paid_unpaid_interest = min(available_payment, unpaid_interest)
        unpaid_interest -= paid_unpaid_interest
        available_payment -= paid_unpaid_interest

        principal_payment = min(available_payment, balance)
        balance = max(0.0, balance - principal_payment)
        actual_payment = paid_current_interest + paid_unpaid_interest + principal_payment

        rows.append(
            PaymentRow(
                month=month,
                year=year,
                annual_rate=annual_rate,
                payment=actual_payment,
                scheduled_payment=payment,
                interest=interest,
                unpaid_generated=unpaid_generated,
                paid_unpaid_interest=paid_unpaid_interest,
                principal=principal_payment,
                balance=balance,
                unpaid_interest=unpaid_interest,
                total_debt=balance + unpaid_interest,
            )
        )

    return rows


def yen(value: float) -> str:
    return f"{round(value):,} 円"


def parse_rates(value: str) -> list[float]:
    rates = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not rates:
        raise argparse.ArgumentTypeError("金利を1つ以上指定してください")
    return rates


def parse_rate_periods(value: str) -> list[tuple[float, int]]:
    periods: list[tuple[float, int]] = []
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        try:
            rate_text, years_text = item.split(":", maxsplit=1)
            rate = float(rate_text.strip())
            years = int(years_text.strip())
        except ValueError as exc:
            raise argparse.ArgumentTypeError(
                "金利期間は '年利:継続年数' をカンマ区切りで指定してください。例: 0.7:5,0.8:10,1.0:20"
            ) from exc

        if rate < 0:
            raise argparse.ArgumentTypeError("年利は0以上で指定してください")
        if years <= 0:
            raise argparse.ArgumentTypeError("継続年数は1以上の整数で指定してください")
        periods.append((rate, years))

    if not periods:
        raise argparse.ArgumentTypeError("金利期間を1つ以上指定してください")
    return periods


def expand_rate_periods(periods: list[tuple[float, int]], term_years: int) -> list[float]:
    rates: list[float] = []
    for rate, years in periods:
        for _ in range(years):
            if len(rates) >= term_years:
                break
            rates.append(rate)

    if not rates:
        raise ValueError("periods must contain at least one year")

    while len(rates) < term_years:
        rates.append(periods[-1][0])

    return rates


def make_points(values: list[float], width: int, height: int, padding: int) -> list[tuple[float, float]]:
    if not values:
        return []

    max_value = max(values)
    if max_value <= 0:
        max_value = 1

    usable_width = width - padding * 2
    usable_height = height - padding * 2
    denom = max(1, len(values) - 1)

    return [
        (
            padding + usable_width * index / denom,
            padding + usable_height * (1 - value / max_value),
        )
        for index, value in enumerate(values)
    ]


def polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def chart_svg(rows: list[PaymentRow], width: int = 1120, height: int = 484) -> str:
    padding = 58
    balances = [row.total_debt for row in rows]
    payments = [row.scheduled_payment for row in rows]
    paid_interests = [row.paid_unpaid_interest + min(row.payment, row.interest) for row in rows]
    balance_points = make_points(balances, width, height, padding)
    payment_points = make_points(payments, width, height, padding)
    interest_points = make_points(paid_interests, width, height, padding)
    max_balance = max(balances) if balances else 0
    max_payment = max(payments + paid_interests) if payments else 0
    plot_bottom = height - padding
    plot_left = padding
    plot_right = width - padding

    year_markers = []
    for row in rows:
        if (row.month - 1) % 12 == 0:
            x = balance_points[row.month - 1][0]
            year_markers.append(
                f'<line x1="{x:.1f}" y1="{padding}" x2="{x:.1f}" y2="{plot_bottom}" '
                'stroke="#e5e7eb" stroke-width="1" />'
                f'<text x="{x:.1f}" y="{height - 20}" text-anchor="middle" '
                'font-size="12" fill="#6b7280">'
                f'{row.year}年</text>'
            )

    return f"""
<svg viewBox="0 0 {width} {height}" role="img" aria-label="残高推移と毎月返済額のグラフ">
  <rect width="{width}" height="{height}" fill="#ffffff" rx="8" />
  <line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_right}" y2="{plot_bottom}" stroke="#9ca3af" />
  <line x1="{plot_left}" y1="{padding}" x2="{plot_left}" y2="{plot_bottom}" stroke="#9ca3af" />
  <line x1="{plot_right}" y1="{padding}" x2="{plot_right}" y2="{plot_bottom}" stroke="#9ca3af" />
  {''.join(year_markers)}
  <text x="{plot_left}" y="28" font-size="14" fill="#2563eb">残高: 最大 {html.escape(yen(max_balance))}</text>
  <text x="{plot_right}" y="28" text-anchor="end" font-size="14" fill="#dc2626">月返済額: 最大 {html.escape(yen(max_payment))}</text>
  <polyline points="{polyline(balance_points)}" fill="none" stroke="#2563eb" stroke-width="3" />
  <polyline points="{polyline(payment_points)}" fill="none" stroke="#dc2626" stroke-width="2.5" stroke-dasharray="7 5" />
  <polyline points="{polyline(interest_points)}" fill="none" stroke="#b7791f" stroke-width="2.25" stroke-dasharray="3 5" />
  <text x="{width - 18}" y="{height - 14}" text-anchor="end" font-size="11" fill="#667085">{html.escape(COPYRIGHT_NOTICE)}</text>
</svg>
""".strip()


def summary(rows: list[PaymentRow], principal: float) -> dict[str, float]:
    total_payment = sum(row.payment for row in rows)
    total_interest = sum(row.interest for row in rows)
    max_payment = max((row.scheduled_payment for row in rows), default=0)
    min_payment = min((row.scheduled_payment for row in rows), default=0)
    max_unpaid_interest = max((row.unpaid_interest for row in rows), default=0)
    final_debt = rows[-1].total_debt if rows else 0
    return {
        "principal": principal,
        "total_payment": total_payment,
        "total_interest": total_interest,
        "max_payment": max_payment,
        "min_payment": min_payment,
        "max_unpaid_interest": max_unpaid_interest,
        "final_debt": final_debt,
    }


def yearly_table(rows: list[PaymentRow]) -> str:
    parts = []
    for year in sorted({row.year for row in rows}):
        year_rows = [row for row in rows if row.year == year]
        first = year_rows[0]
        last = year_rows[-1]
        parts.append(
            "<tr>"
            f"<td>{year}</td>"
            f"<td>{first.annual_rate:.3f}%</td>"
            f"<td>{html.escape(yen(first.scheduled_payment))}</td>"
            f"<td>{html.escape(yen(sum(row.interest for row in year_rows)))}</td>"
            f"<td>{html.escape(yen(last.balance))}</td>"
            f"<td>{html.escape(yen(last.unpaid_interest))}</td>"
            "</tr>"
        )
    return "\n".join(parts)


def monthly_table(rows: list[PaymentRow]) -> str:
    return "\n".join(
        "<tr>"
        f"<td>{row.month}</td>"
        f"<td>{row.year}</td>"
        f"<td>{row.annual_rate:.3f}%</td>"
        f"<td>{html.escape(yen(row.scheduled_payment))}</td>"
        f"<td>{html.escape(yen(row.payment))}</td>"
        f"<td>{html.escape(yen(row.interest))}</td>"
        f"<td>{html.escape(yen(row.principal))}</td>"
        f"<td>{html.escape(yen(row.balance))}</td>"
        f"<td>{html.escape(yen(row.unpaid_interest))}</td>"
        "</tr>"
        for row in rows
    )


def write_html_report(
    rows: list[PaymentRow],
    principal: float,
    term_years: int,
    annual_rates: list[float],
    output: Path,
) -> None:
    stats = summary(rows, principal)
    rates_json = html.escape(json.dumps(annual_rates, ensure_ascii=False))
    content = f"""<!doctype html>
<!-- {COPYRIGHT_NOTICE} -->
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ローンシミュレーション</title>
  <style>
    body {{
      margin: 0;
      background: #f8fafc;
      color: #111827;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 28px auto 48px;
    }}
    h1 {{ font-size: 28px; margin: 0 0 18px; }}
    h2 {{ font-size: 18px; margin: 28px 0 12px; }}
    .panel {{
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 18px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.05);
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .metric {{
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 12px;
    }}
    .metric span {{
      display: block;
      color: #6b7280;
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric strong {{ font-size: 20px; }}
    .chart {{ overflow-x: auto; }}
    .chart svg {{ min-width: 820px; width: 100%; height: auto; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: #ffffff;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      overflow: hidden;
      font-size: 14px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid #e5e7eb;
      text-align: right;
      white-space: nowrap;
    }}
    th {{
      background: #f3f4f6;
      color: #374151;
      font-weight: 600;
    }}
    th:first-child, td:first-child {{ text-align: left; }}
    .table-wrap {{ overflow-x: auto; }}
    .note {{ color: #4b5563; font-size: 13px; line-height: 1.6; }}
    .site-footer {{
      width: min(1180px, calc(100vw - 32px));
      margin: -24px auto 32px;
      color: #6b7280;
      font-size: 12px;
      text-align: right;
    }}
  </style>
</head>
<body>
<main>
  <h1>ローンシミュレーション</h1>
  <section class="panel">
    <div class="metrics">
      <div class="metric"><span>借入額</span><strong>{html.escape(yen(stats["principal"]))}</strong></div>
      <div class="metric"><span>借入期間</span><strong>{term_years} 年</strong></div>
      <div class="metric"><span>総返済額</span><strong>{html.escape(yen(stats["total_payment"]))}</strong></div>
      <div class="metric"><span>総利息</span><strong>{html.escape(yen(stats["total_interest"]))}</strong></div>
      <div class="metric"><span>月返済額範囲</span><strong>{html.escape(yen(stats["min_payment"]))} - {html.escape(yen(stats["max_payment"]))}</strong></div>
      <div class="metric"><span>最大未払利息</span><strong>{html.escape(yen(stats["max_unpaid_interest"]))}</strong></div>
      <div class="metric"><span>期末残債</span><strong>{html.escape(yen(stats["final_debt"]))}</strong></div>
    </div>
    <div class="chart">{chart_svg(rows)}</div>
    <p class="note">青線はローン残高、赤の破線は毎月の返済額です。金利設定は年利 {rates_json}% として扱い、指定がない年は最後の金利を継続しています。変動金利は5年ルール・125%ルール・未払利息ありで計算します。</p>
  </section>

  <h2>年次サマリー</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr><th>年</th><th>年利</th><th>月返済額</th><th>年間利息</th><th>年末元金残高</th><th>年末未払利息</th></tr>
      </thead>
      <tbody>
        {yearly_table(rows)}
      </tbody>
    </table>
  </div>

  <h2>月次明細</h2>
  <div class="table-wrap">
    <table>
      <thead>
        <tr><th>月</th><th>年</th><th>年利</th><th>予定返済額</th><th>実返済額</th><th>利息</th><th>元金</th><th>元金残高</th><th>未払利息</th></tr>
      </thead>
      <tbody>
        {monthly_table(rows)}
      </tbody>
    </table>
  </div>
</main>
<footer class="site-footer">{COPYRIGHT_NOTICE}</footer>
</body>
</html>
"""
    output.write_text(content, encoding="utf-8")


def write_csv(rows: list[PaymentRow], output: Path) -> None:
    with output.open("w", newline="", encoding="utf-8-sig") as file:
        file.write(f"# {COPYRIGHT_NOTICE}\n")
        writer = csv.writer(file)
        writer.writerow(
            [
                "month",
                "year",
                "annual_rate",
                "scheduled_payment",
                "actual_payment",
                "interest",
                "unpaid_generated",
                "paid_unpaid_interest",
                "principal",
                "principal_balance",
                "unpaid_interest",
                "total_debt",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.month,
                    row.year,
                    f"{row.annual_rate:.6f}",
                    f"{row.scheduled_payment:.2f}",
                    f"{row.payment:.2f}",
                    f"{row.interest:.2f}",
                    f"{row.unpaid_generated:.2f}",
                    f"{row.paid_unpaid_interest:.2f}",
                    f"{row.principal:.2f}",
                    f"{row.balance:.2f}",
                    f"{row.unpaid_interest:.2f}",
                    f"{row.total_debt:.2f}",
                ]
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ローン残高と月返済額をシミュレーションします。")
    parser.add_argument("--principal", type=float, required=True, help="借入額。例: 35000000")
    parser.add_argument("--term-years", type=int, required=True, help="借入期間。例: 35")
    rate_group = parser.add_mutually_exclusive_group(required=True)
    rate_group.add_argument(
        "--rate-periods",
        type=parse_rate_periods,
        help="金利と継続年数を '年利:継続年数' のカンマ区切りで指定。例: 0.7:5,0.8:10,1.0:20",
    )
    rate_group.add_argument(
        "--rates",
        type=parse_rates,
        help="後方互換用。年ごとの年利をカンマ区切りで指定。例: 0.7,0.9,1.1",
    )
    parser.add_argument("--html", type=Path, default=Path("loan_simulation.html"), help="HTML出力先")
    parser.add_argument("--csv", type=Path, default=Path("loan_schedule.csv"), help="CSV出力先")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    rates = expand_rate_periods(args.rate_periods, args.term_years) if args.rate_periods else args.rates
    rows = simulate_loan(args.principal, args.term_years, rates)
    write_html_report(rows, args.principal, args.term_years, rates, args.html)
    write_csv(rows, args.csv)

    stats = summary(rows, args.principal)
    print(f"HTML: {args.html}")
    print(f"CSV : {args.csv}")
    print(f"総返済額: {yen(stats['total_payment'])}")
    print(f"総利息  : {yen(stats['total_interest'])}")
    print(f"月返済額: {yen(stats['min_payment'])} - {yen(stats['max_payment'])}")
    print(f"最大未払利息: {yen(stats['max_unpaid_interest'])}")
    print(f"期末残債: {yen(stats['final_debt'])}")


if __name__ == "__main__":
    main()
