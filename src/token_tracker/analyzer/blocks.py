from datetime import UTC, datetime, timedelta

from ..adapters.types import DailyStats, P90Limits, SessionBlock, UsageEntry
from .aggregator import add_token_fields
from .cost import calculate_cost

BLOCK_DURATION = timedelta(hours=5)


def analyze_blocks(entries: list[UsageEntry]) -> list[SessionBlock]:
    if not entries:
        return []

    sorted_entries = sorted(entries, key=lambda e: e.timestamp)
    blocks: list[SessionBlock] = []
    current_block: SessionBlock | None = None

    for entry in sorted_entries:
        if current_block is None or entry.timestamp >= current_block.end_time:
            if current_block and entry.timestamp >= current_block.end_time:
                gap_duration = entry.timestamp - current_block.end_time
                if gap_duration > timedelta(minutes=5):
                    gap = SessionBlock(
                        start_time=current_block.end_time,
                        end_time=entry.timestamp,
                        is_gap=True,
                    )
                    blocks.append(gap)

            current_block = SessionBlock(
                start_time=entry.timestamp,
                end_time=entry.timestamp + BLOCK_DURATION,
            )
            blocks.append(current_block)

        current_block.entries.append(entry)
        add_token_fields(current_block, entry, calculate_cost(entry))

    now = datetime.now(UTC)
    for block in blocks:
        if block.is_gap:
            continue
        if block.end_time > now and block.entries:
            block.is_active = True
            elapsed = (now - block.start_time).total_seconds() / 60
            if elapsed > 0:
                block.burn_rate = block.total_tokens / elapsed

    return blocks


def calculate_p90(daily_stats: list[DailyStats]) -> P90Limits:
    if len(daily_stats) < 3:
        return P90Limits()

    token_values = sorted(d.total_tokens for d in daily_stats)
    cost_values = sorted(d.cost_usd for d in daily_stats)
    msg_values = sorted(d.message_count for d in daily_stats)

    def p90(values: list) -> float:
        idx = int(len(values) * 0.9)
        return values[min(idx, len(values) - 1)]

    return P90Limits(
        token_limit=int(p90(token_values)),
        cost_limit=round(p90(cost_values), 2),
        message_limit=int(p90(msg_values)),
    )
