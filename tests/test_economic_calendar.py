import json

from economic_calendar import (
    EconomicCalendarEvent,
    build_calendar_payload,
    normalize_api_event,
    parse_trading_economics_html,
    preserve_generated_at_when_events_unchanged,
    write_json_atomic,
)


def test_normalize_api_event_populates_market_values():
    event = normalize_api_event(
        {
            "CalendarId": "87220",
            "Date": "2026-05-08T12:30:00",
            "Country": "United States",
            "Category": "Non Farm Payrolls",
            "Event": "Non Farm Payrolls",
            "Reference": "Apr",
            "Actual": "177K",
            "Previous": "185K",
            "Forecast": "130K",
            "TEForecast": "125K",
            "Source": "U.S. Bureau of Labor Statistics",
            "SourceURL": "https://www.bls.gov/",
            "URL": "/united-states/non-farm-payrolls",
            "Importance": 3,
            "LastUpdate": "2026-05-08T12:31:00",
            "Revised": "228K",
        }
    )

    assert event.actual == "177K"
    assert event.previous == "185K"
    assert event.estimate == "130K"
    assert event.forecast == "130K"
    assert event.te_forecast == "125K"
    assert event.display_event == "Non Farm Payrolls"
    assert event.interval == ""
    assert event.chart_label == "Non Farm Payrolls"
    assert event.source_url == "https://www.bls.gov/"
    assert event.url == "https://tradingeconomics.com/united-states/non-farm-payrolls"


def test_normalize_api_event_extracts_interval_labels():
    event = normalize_api_event(
        {
            "CalendarId": "2",
            "Date": "2026-06-01T14:00:00",
            "Country": "United States",
            "Category": "Construction Spending MoM",
            "Event": "Construction Spending MoM",
            "Actual": "0.4%",
            "Previous": "0.6%",
            "Forecast": "0.2%",
            "URL": "/united-states/construction-spending",
        }
    )

    assert event.display_event == "Construction Spending"
    assert event.interval == "MoM"
    assert event.interval_label == "MoM"
    assert event.chart_label == "Construction Spending (MoM)"
    assert event.chart_url


def test_normalize_api_event_extracts_dod_interval_labels():
    event = normalize_api_event(
        {
            "CalendarId": "22",
            "Date": "2026-06-01T14:00:00",
            "Country": "United States",
            "Category": "Retail Sales DoD",
            "Event": "Retail Sales DoD",
            "Actual": "0.3%",
            "Previous": "0.1%",
            "Forecast": "0.2%",
            "URL": "/united-states/retail-sales",
        }
    )

    assert event.display_event == "Retail Sales"
    assert event.interval == "DoD"
    assert event.chart_label == "Retail Sales (DoD)"


def test_plain_rate_events_show_level_interval():
    event = normalize_api_event(
        {
            "CalendarId": "3",
            "Date": "2026-06-01T14:00:00",
            "Country": "United States",
            "Category": "Interest Rate",
            "Event": "Fed Interest Rate Decision",
            "Actual": "4.50%",
            "Previous": "4.50%",
            "Forecast": "4.50%",
            "URL": "/united-states/interest-rate",
        }
    )

    assert event.display_event == "Fed Interest Rate Decision"
    assert event.interval == "Level"
    assert event.chart_label == "Fed Interest Rate Decision (Level)"


def test_rate_category_does_not_mark_speeches_as_level():
    event = normalize_api_event(
        {
            "CalendarId": "4",
            "Date": "2026-06-01T16:00:00",
            "Country": "United States",
            "Category": "Interest Rate",
            "Event": "Fed Powell Speech",
            "URL": "/united-states/interest-rate",
        }
    )

    assert event.display_event == "Fed Powell Speech"
    assert event.interval == ""
    assert event.chart_label == "Fed Powell Speech"


def test_mortgage_applications_do_not_use_rate_level_interval():
    event = normalize_api_event(
        {
            "CalendarId": "5",
            "Date": "2026-06-01T16:00:00",
            "Country": "United States",
            "Category": "Mortgage Applications",
            "Event": "MBA Mortgage Applications",
            "URL": "/united-states/mortgage-applications",
        }
    )

    assert event.interval == ""
    assert event.chart_label == "MBA Mortgage Applications"


def test_html_parser_extracts_previous_estimate_and_actual():
    html = """
    <table>
      <tr data-url="/united-states/inflation-cpi"
          data-id="123"
          data-country="united states"
          data-category="inflation rate"
          data-event="inflation rate yoy"
          data-symbol="USCPI">
        <td class=" 2026-05-25"><span>08:30 AM</span></td>
        <td><table><tr><td>US</td></tr></table></td>
        <td>
          <a class="calendar-event" href="/united-states/inflation-cpi">Inflation Rate YoY</a>
          <span class="calendar-reference">APR</span>
        </td>
        <td><span id="actual">3.4%</span></td>
        <td><span id="previous">3.5%</span><span id="revised">3.6%</span></td>
        <td><a id="consensus" href="/united-states/inflation-cpi">3.3%</a></td>
        <td><a id="forecast" href="/united-states/inflation-cpi">3.2%</a></td>
      </tr>
    </table>
    """

    events = parse_trading_economics_html(html)

    assert len(events) == 1
    assert events[0].date == "2026-05-25"
    assert events[0].time == "08:30 AM"
    assert events[0].event == "Inflation Rate YoY"
    assert events[0].display_event == "Inflation Rate"
    assert events[0].interval == "YoY"
    assert events[0].chart_label == "Inflation Rate (YoY)"
    assert events[0].reference == "APR"
    assert events[0].actual == "3.4%"
    assert events[0].previous == "3.5%"
    assert events[0].estimate == "3.3%"
    assert events[0].forecast == "3.2%"
    assert events[0].revised == "3.6%"


def test_write_calendar_json_payload(tmp_path):
    event = normalize_api_event(
        {
            "CalendarId": "1",
            "Date": "2026-05-25T08:30:00",
            "Country": "United States",
            "Event": "Durable Goods Orders",
            "Actual": "9.2%",
            "Previous": "-8.1%",
            "Forecast": "8.0%",
        }
    )
    payload = build_calendar_payload([event], "https://example.com/calendar")
    output = tmp_path / "economic_calendar.json"

    write_json_atomic(payload, output)
    saved = json.loads(output.read_text(encoding="utf-8"))

    assert saved["source_url"] == "https://example.com/calendar"
    assert saved["events"][0]["actual"] == "9.2%"
    assert saved["events"][0]["previous"] == "-8.1%"
    assert saved["events"][0]["estimate"] == "8.0%"


def test_preserve_generated_at_when_events_do_not_change(tmp_path):
    output = tmp_path / "economic_calendar.json"
    previous_payload = {
        "generated_at": "2026-05-25T12:00:00+00:00",
        "source": "Trading Economics",
        "source_url": "https://example.com/calendar",
        "events": [{"event_id": "1", "actual": "1.0%"}],
    }
    output.write_text(json.dumps(previous_payload), encoding="utf-8")

    next_payload = {
        "generated_at": "2026-05-25T12:15:00+00:00",
        "source": "Trading Economics",
        "source_url": "https://example.com/calendar",
        "events": [{"event_id": "1", "actual": "1.0%"}],
    }

    preserved = preserve_generated_at_when_events_unchanged(next_payload, output)

    assert preserved["generated_at"] == "2026-05-25T12:00:00+00:00"


def test_calendar_payload_sorts_by_release_time():
    later = EconomicCalendarEvent(
        event_id="2",
        date="2026-05-25",
        time="12:30 PM",
        country="United States",
        category="Labor",
        event="Afternoon Release",
        display_event="Afternoon Release",
        reference="",
        interval="",
        interval_label="",
        actual="",
        previous="",
        estimate="",
        forecast="",
        te_forecast="",
        revised="",
        importance="",
        source="",
        source_url="",
        url="",
        chart_label="Afternoon Release",
        chart_url="",
        last_update="",
    )
    earlier = EconomicCalendarEvent(
        event_id="1",
        date="2026-05-25",
        time="08:30 AM",
        country="United States",
        category="Labor",
        event="Morning Release",
        display_event="Morning Release",
        reference="",
        interval="",
        interval_label="",
        actual="",
        previous="",
        estimate="",
        forecast="",
        te_forecast="",
        revised="",
        importance="",
        source="",
        source_url="",
        url="",
        chart_label="Morning Release",
        chart_url="",
        last_update="",
    )

    payload = build_calendar_payload([later, earlier], "https://example.com/calendar")

    assert [event["event_id"] for event in payload["events"]] == ["1", "2"]
