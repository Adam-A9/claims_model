import argparse
import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_PATH = BASE_DIR / "docs" / "economic_calendar.json"
TRADING_ECONOMICS_API_BASE = "https://api.tradingeconomics.com/calendar/country"
TRADING_ECONOMICS_WEB_BASE = "https://tradingeconomics.com"
DEFAULT_COUNTRY = "United States"
DEFAULT_USER_AGENT = "claims-model-economic-calendar/1.0"
INTERVAL_LABELS = {
    "DOD": "DoD",
    "WOW": "WoW",
    "MOM": "MoM",
    "QOQ": "QoQ",
    "YOY": "YoY",
    "YTD": "YTD",
    "SAAR": "SAAR",
}
INTERVAL_PATTERN = re.compile(r"\b(DoD|WoW|MoM|QoQ|YoY|YTD|SAAR)\b", re.IGNORECASE)
RATE_LEVEL_PATTERN = re.compile(
    r"\b(interest rate|mortgage rate|rate decision|fed funds|yield|auction|spread|treasury|bond)\b",
    re.IGNORECASE,
)


@dataclass
class EconomicCalendarEvent:
    event_id: str
    date: str
    time: str
    country: str
    category: str
    event: str
    display_event: str
    reference: str
    interval: str
    interval_label: str
    actual: str
    previous: str
    estimate: str
    forecast: str
    te_forecast: str
    revised: str
    importance: str
    source: str
    source_url: str
    url: str
    chart_label: str
    chart_url: str
    last_update: str


def clean_value(value) -> str:
    if value is None:
        return ""
    text = unescape(str(value)).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def first_value(*values) -> str:
    for value in values:
        cleaned = clean_value(value)
        if cleaned:
            return cleaned
    return ""


def absolute_te_url(value: str) -> str:
    value = clean_value(value)
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return f"{TRADING_ECONOMICS_WEB_BASE}{value}"
    return value


def build_chart_url(event_id: str, event_url: str) -> str:
    event_id = clean_value(event_id)
    event_url = clean_value(event_url)
    if not event_id or not event_url.startswith("https://tradingeconomics.com/"):
        return ""
    path = event_url.replace(TRADING_ECONOMICS_WEB_BASE, "", 1)
    return (
        "https://d3fy651gv2fhd3.cloudfront.net/charts/"
        f"calendar-{event_id}.png?h=80&w=160&n=4&y=0&y2=0&x=0"
        f"&title=false&lbl=0&bg=0&v=V20230410&url={quote(path, safe='/')}"
    )


def interval_from_text(*values: str) -> str:
    for value in values:
        match = INTERVAL_PATTERN.search(clean_value(value))
        if match:
            return INTERVAL_LABELS[match.group(1).upper()]
    return ""


def is_rate_level_event(*values: str) -> bool:
    event_text = clean_value(values[0] if values else "")
    return bool(RATE_LEVEL_PATTERN.search(event_text))


def infer_interval(event: str, category: str) -> str:
    explicit_interval = interval_from_text(event, category)
    if explicit_interval:
        return explicit_interval
    if is_rate_level_event(event, category):
        return "Level"
    return ""


def display_event_name(event: str, interval: str) -> str:
    event = clean_value(event)
    if not event or interval == "Level":
        return event

    pattern = re.compile(rf"\b{re.escape(interval)}\b", re.IGNORECASE)
    display_event = clean_value(pattern.sub("", event))
    return re.sub(r"\s+([,/)])", r"\1", display_event)


def add_interval_metadata(event: EconomicCalendarEvent) -> EconomicCalendarEvent:
    event.interval = infer_interval(event.event, event.category)
    event.interval_label = event.interval
    event.display_event = display_event_name(event.event, event.interval)
    event.chart_label = first_value(
        f"{event.display_event} ({event.interval_label})" if event.interval_label else "",
        event.display_event,
    )
    event.chart_url = first_value(event.chart_url, build_chart_url(event.event_id, event.url))
    return event


def split_api_datetime(value: str) -> tuple[str, str]:
    cleaned = clean_value(value)
    if not cleaned:
        return "", ""
    normalized = cleaned.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.date().isoformat(), parsed.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        parts = cleaned.split("T", 1)
        if len(parts) == 2:
            return parts[0], parts[1][:5]
        return cleaned, ""


def normalize_api_event(row: dict) -> EconomicCalendarEvent:
    event_date, event_time = split_api_datetime(row.get("Date"))
    consensus = first_value(row.get("Forecast"), row.get("Consensus"))
    te_forecast = clean_value(row.get("TEForecast"))

    return add_interval_metadata(EconomicCalendarEvent(
        event_id=clean_value(row.get("CalendarId")),
        date=event_date,
        time=event_time,
        country=clean_value(row.get("Country")),
        category=clean_value(row.get("Category")),
        event=clean_value(row.get("Event")),
        display_event="",
        reference=clean_value(row.get("Reference")),
        interval="",
        interval_label="",
        actual=clean_value(row.get("Actual")),
        previous=clean_value(row.get("Previous")),
        estimate=first_value(consensus, te_forecast),
        forecast=consensus,
        te_forecast=te_forecast,
        revised=clean_value(row.get("Revised")),
        importance=clean_value(row.get("Importance")),
        source=clean_value(row.get("Source")),
        source_url=absolute_te_url(row.get("SourceURL")),
        url=absolute_te_url(row.get("URL")),
        chart_label="",
        chart_url="",
        last_update=clean_value(row.get("LastUpdate")),
    ))


class TradingEconomicsCalendarParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events: list[EconomicCalendarEvent] = []
        self._row = None
        self._row_date = ""
        self._cell_depth = 0
        self._cell_index = -1
        self._cell_parts: list[str] = []
        self._cells: list[str] = []
        self._captures: list[tuple[str, str]] = []
        self._fields: dict[str, list[str]] = {}
        self._chart_url = ""
        self._row_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = {key: value or "" for key, value in attrs}

        if tag == "tr" and attrs_dict.get("data-id"):
            self._row = attrs_dict
            self._row_date = ""
            self._cell_depth = 0
            self._cell_index = -1
            self._cell_parts = []
            self._cells = []
            self._captures = []
            self._fields = {}
            self._chart_url = ""
            self._row_depth = 0
            return

        if self._row is None:
            return

        if tag == "tr":
            self._row_depth += 1
            return

        if tag == "td":
            if self._cell_depth == 0:
                self._cell_index += 1
                self._cell_parts = []
                if self._cell_index == 0:
                    self._row_date = self._date_from_class(attrs_dict.get("class", ""))
            self._cell_depth += 1

        chart_url = attrs_dict.get("data-src", "")
        if chart_url and "calendar-" in chart_url:
            self._chart_url = absolute_te_url(chart_url)

        field = self._capture_field(tag, attrs_dict)
        if field:
            self._fields.setdefault(field, [])
            self._captures.append((tag, field))

    def handle_endtag(self, tag):
        if self._row is None:
            return

        if self._captures and self._captures[-1][0] == tag:
            self._captures.pop()

        if tag == "td" and self._cell_depth > 0:
            self._cell_depth -= 1
            if self._cell_depth == 0:
                self._cells.append(clean_value(" ".join(self._cell_parts)))

        if tag == "tr" and self._row_depth > 0:
            self._row_depth -= 1
            return

        if tag == "tr":
            self._finish_row()

    def handle_data(self, data):
        if self._row is None:
            return
        if self._cell_depth > 0:
            self._cell_parts.append(data)
        if self._captures:
            self._fields[self._captures[-1][1]].append(data)

    def _finish_row(self):
        event_url = absolute_te_url(self._row.get("data-url", ""))
        event = add_interval_metadata(EconomicCalendarEvent(
            event_id=clean_value(self._row.get("data-id")),
            date=self._row_date,
            time=self._cell(0),
            country=clean_value(self._row.get("data-country")).title(),
            category=clean_value(self._row.get("data-category")).title(),
            event=first_value(self._field("event"), clean_value(self._row.get("data-event")).title()),
            display_event="",
            reference=self._field("reference"),
            interval="",
            interval_label="",
            actual=self._field("actual"),
            previous=self._field("previous"),
            estimate=first_value(self._field("consensus"), self._field("forecast")),
            forecast=self._field("forecast"),
            te_forecast="",
            revised=self._field("revised"),
            importance="",
            source="Trading Economics",
            source_url=event_url,
            url=event_url,
            chart_label="",
            chart_url=self._chart_url,
            last_update="",
        ))
        if event.event_id and event.event:
            self.events.append(event)
        self._row = None

    def _cell(self, index: int) -> str:
        if index >= len(self._cells):
            return ""
        return self._cells[index]

    def _field(self, name: str) -> str:
        return clean_value(" ".join(self._fields.get(name, [])))

    @staticmethod
    def _date_from_class(value: str) -> str:
        match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", value)
        return match.group(0) if match else ""

    @staticmethod
    def _capture_field(tag: str, attrs: dict) -> str:
        element_id = attrs.get("id", "")
        if element_id in {"actual", "previous", "revised", "consensus", "forecast"}:
            return element_id

        classes = set(attrs.get("class", "").split())
        if tag == "a" and "calendar-event" in classes:
            return "event"
        if tag == "span" and "calendar-reference" in classes:
            return "reference"
        return ""


def parse_trading_economics_html(html: str) -> list[EconomicCalendarEvent]:
    parser = TradingEconomicsCalendarParser()
    parser.feed(html)
    return parser.events


def fetch_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Unable to fetch economic calendar data from {url}: {exc}") from exc


def fetch_api_calendar(
    api_key: str,
    country: str,
    start_date: date,
    end_date: date,
    importance: str = "",
) -> tuple[list[EconomicCalendarEvent], str]:
    country_segment = quote(country, safe=",")
    url = (
        f"{TRADING_ECONOMICS_API_BASE}/{country_segment}/"
        f"{start_date.isoformat()}/{end_date.isoformat()}"
    )
    params = {"c": api_key, "f": "json", "values": "true"}
    if importance:
        params["importance"] = importance
    url = f"{url}?{urlencode(params)}"
    payload = json.loads(fetch_url(url))
    if not isinstance(payload, list):
        raise RuntimeError("Trading Economics API returned an unexpected payload")
    return [normalize_api_event(row) for row in payload], url


def fetch_html_calendar(country: str = DEFAULT_COUNTRY) -> tuple[list[EconomicCalendarEvent], str]:
    country_slug = country.lower().replace(" ", "-")
    url = f"{TRADING_ECONOMICS_WEB_BASE}/{country_slug}/calendar/api?source=calendar"
    return parse_trading_economics_html(fetch_url(url)), url


def sort_events(events: Iterable[EconomicCalendarEvent]) -> list[EconomicCalendarEvent]:
    def sort_key(event: EconomicCalendarEvent):
        return (event.date or "9999-99-99", time_sort_value(event.time), event.country, event.event)

    return sorted(events, key=sort_key)


def time_sort_value(value: str) -> str:
    cleaned = clean_value(value)
    if not cleaned:
        return "99:99"
    for pattern in ("%I:%M %p", "%H:%M"):
        try:
            return datetime.strptime(cleaned.upper(), pattern).strftime("%H:%M")
        except ValueError:
            continue
    return "99:99"


def build_calendar_payload(events: list[EconomicCalendarEvent], source_url: str) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Trading Economics",
        "source_url": source_url,
        "events": [asdict(event) for event in sort_events(events)],
    }


def write_json_atomic(payload: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=output_path.parent,
        delete=False,
        newline="\n",
    ) as temp_file:
        json.dump(payload, temp_file, indent=2, ensure_ascii=False)
        temp_file.write("\n")
        temp_name = temp_file.name
    Path(temp_name).replace(output_path)


def preserve_generated_at_when_events_unchanged(payload: dict, output_path: Path) -> dict:
    if not output_path.exists():
        return payload

    try:
        previous_payload = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload

    if previous_payload.get("events") == payload.get("events"):
        payload = dict(payload)
        payload["generated_at"] = previous_payload.get("generated_at")
    return payload


def collect_calendar(
    country: str,
    start_date: date,
    end_date: date,
    importance: str,
    source: str,
    api_key: str,
) -> tuple[list[EconomicCalendarEvent], str]:
    if source in {"auto", "api"} and api_key:
        try:
            return fetch_api_calendar(api_key, country, start_date, end_date, importance)
        except RuntimeError:
            if source == "api":
                raise
            LOGGER.warning("Trading Economics API fetch failed; falling back to HTML calendar")

    if source == "api":
        raise RuntimeError(
            "ECONOMIC_CALENDAR_API_KEY or TRADING_ECONOMICS_API_KEY is required for API mode"
        )

    LOGGER.info("Using Trading Economics HTML calendar fallback")
    return fetch_html_calendar(country)


def parse_args():
    parser = argparse.ArgumentParser(description="Fetch and normalize the economic calendar.")
    parser.add_argument("--country", default=DEFAULT_COUNTRY)
    parser.add_argument("--days-back", type=int, default=2)
    parser.add_argument("--days-forward", type=int, default=14)
    parser.add_argument("--importance", default="")
    parser.add_argument("--source", choices=["auto", "api", "html"], default="auto")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    args = parse_args()
    today = date.today()
    api_key = first_value(
        os.getenv("ECONOMIC_CALENDAR_API_KEY"),
        os.getenv("TRADING_ECONOMICS_API_KEY"),
    )
    events, source_url = collect_calendar(
        country=args.country,
        start_date=today - timedelta(days=args.days_back),
        end_date=today + timedelta(days=args.days_forward),
        importance=args.importance,
        source=args.source,
        api_key=api_key,
    )
    payload = build_calendar_payload(events, source_url)
    payload = preserve_generated_at_when_events_unchanged(payload, args.output)
    write_json_atomic(payload, args.output)
    LOGGER.info("Wrote %s events to %s", len(events), args.output)


if __name__ == "__main__":
    main()
