"""TAP Ticket Dashboard

Run with:  .venv/bin/streamlit run app.py
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_PATH = Path(__file__).parent / "data" / "TAP_Desk_cleaned.xlsx"
HIGH_PRIORITIES = ["High", "Critical"]
RELEASE_DATE = pd.Timestamp("2025-10-01")  # major product release

# Original source columns
ORIGINAL_COLUMNS = [
    "Issue Key", "Issue Type", "Summary", "Status", "Priority", "Component",
    "Reporter", "Assignee", "Customer", "Created", "Resolved",
    "Reopen Count", "Labels", "Comment Count",
]

st.set_page_config(
    page_title="TAP Desk Dashboard",
    layout="wide",
    initial_sidebar_state="collapsed",
)


@st.cache_data
def load_data() -> pd.DataFrame:
    """Read the cleaned tickets sheet. Cached so the file is read once."""
    tickets = pd.read_excel(DATA_PATH, sheet_name="Tickets")
    tickets["Created"] = pd.to_datetime(tickets["Created"])
    tickets["Resolved"] = pd.to_datetime(tickets["Resolved"])
    return tickets


all_tickets = load_data()

# Sidebar 
st.sidebar.header("Filters")

min_date = all_tickets["Created"].min().date()
max_date = all_tickets["Created"].max().date()
date_range = st.sidebar.date_input(
    "Created date range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date,
)


def multifilter(label: str, column: str) -> list[str]:
    """A multiselect that defaults to all values of a column."""
    options = sorted(all_tickets[column].dropna().unique().tolist())
    return st.sidebar.multiselect(label, options, default=options)


selected_priorities = multifilter("Priority", "Priority")
selected_components = multifilter("Component", "Component")
selected_statuses = multifilter("Status", "Status")
selected_assignees = multifilter("Assignee", "Assignee")

# Apply filters 
row_filter = (
    all_tickets["Priority"].isin(selected_priorities)
    & all_tickets["Component"].isin(selected_components)
    & all_tickets["Status"].isin(selected_statuses)
    & all_tickets["Assignee"].isin(selected_assignees)
)
# date_input returns a single date until both ends are picked
if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
    start_date, end_date = date_range
    row_filter &= all_tickets["Created"].dt.date.between(start_date, end_date)

filtered_tickets = all_tickets[row_filter]


# Focus-score helpers 
def min_max_normalize(values: pd.Series) -> pd.Series:
    """Min-max normalize to 0-1; flat series -> all zeros."""
    value_range = values.max() - values.min()
    return (values - values.min()) / value_range if value_range else values * 0.0


def component_scorecard(tickets: pd.DataFrame) -> pd.DataFrame:
    """One row per component with the signals that argue for investment."""
    tickets = tickets.assign(
        is_high_priority=tickets["Priority"].isin(HIGH_PRIORITIES),
        is_reopened=tickets["Reopen Count"] > 0,
    )
    scorecard = tickets.groupby("Component").agg(
        Tickets=("Issue Key", "size"),
        High_Critical_pct=("is_high_priority", "mean"),
        Median_hrs=("resolution_hours", "median"),
        Reopen_pct=("is_reopened", "mean"),
        Avg_comments=("Comment Count", "mean"),
    )
    scorecard["High_Critical_pct"] *= 100
    scorecard["Reopen_pct"] *= 100
    # Composite "focus score": equal blend of volume, reopens, and severity
    # Speed (median resolution time) is excluded by setting its weight to 0
    weight_tickets, weight_median, weight_reopen, weight_high = 1.0, 0.0, 1.0, 1.0
    scorecard["Focus_score"] = (
        weight_tickets * min_max_normalize(scorecard["Tickets"])
        + weight_median * min_max_normalize(scorecard["Median_hrs"].fillna(0))
        + weight_reopen * min_max_normalize(scorecard["Reopen_pct"])
        + weight_high * min_max_normalize(scorecard["High_Critical_pct"])
    ) / (weight_tickets + weight_median + weight_reopen + weight_high) * 100
    return scorecard.sort_values("Focus_score", ascending=False)


def reopen_by_component(tickets: pd.DataFrame) -> pd.DataFrame:
    """Reopen rate (%) per component, sorted low to high for horizontal bars."""
    return (
        tickets.assign(is_reopened=tickets["Reopen Count"] > 0)
        .groupby("Component")["is_reopened"]
        .mean()
        .mul(100)
        .sort_values()
        .reset_index(name="Reopen %")
    )


def pain_score_table(tickets: pd.DataFrame, min_count: int = 8) -> pd.DataFrame:
    """Pain score for recurring Reported Issues, following the notebook's method.

    Three signals (volume, severity as % High/Critical, reopen rate) are each
    min-max normalized across every qualifying family, then averaged to a 0-100
    score. Reported Issues only, families with at least `min_count` tickets,
    normalized across all components so the score stays relative to the product.

    One refinement over the notebook: issues are grouped on a normalized summary
    (order numbers -> #N, state codes -> {STATE}) so templated families like
    "Tax calculation off for {STATE}" aggregate instead of fragmenting below the
    floor. This leaves single-string families (and the Payments ranking) unchanged.
    """
    reported = tickets[tickets["Issue Type"] == "Reported Issue"].assign(
        Issue=lambda frame: frame["Summary"]
        .str.replace(r"#\d+", "#N", regex=True)
        .str.replace(r"\bfor [A-Z]{2}\b", "for {STATE}", regex=True)
    )
    families = reported.groupby("Issue").agg(
        Component=("Component", lambda s: s.mode().iat[0]),
        Tickets=("Issue Key", "size"),
        high_critical=("Priority", lambda s: s.isin(HIGH_PRIORITIES).mean() * 100),
        reopen=("Reopen Count", lambda s: (s > 0).mean() * 100),
    )
    families = families[families["Tickets"] >= min_count].copy()
    if families.empty:
        return families.reset_index()
    for col in ["Tickets", "high_critical", "reopen"]:
        low, high = families[col].min(), families[col].max()
        families[col + "_z"] = 0.0 if high == low else (families[col] - low) / (high - low)
    families["Pain score"] = (
        (families["Tickets_z"] + families["high_critical_z"] + families["reopen_z"]) / 3 * 100
    ).round()
    families["High/Critical %"] = families["high_critical"].round()
    families["Reopen %"] = families["reopen"].round()
    return families.reset_index().sort_values("Pain score", ascending=False)


# Header
st.title("TAP Ticket Dashboard")
st.caption(
    f"A read on {len(all_tickets):,} support tickets, ranked by where fixing issues pays off most. "
    "Open the sidebar (arrow, top left) to filter and stress-test the conclusion."
)

if filtered_tickets.empty:
    st.warning("No tickets match the current filters. Widen them in the sidebar.")
    st.stop()

# A quick strip to set the scene before the story
is_resolved = filtered_tickets["Status"].eq("Resolved")
kpi_total, kpi_resolved, kpi_median, kpi_reopen = st.columns(4)
kpi_total.metric("Tickets in view", f"{len(filtered_tickets):,}")
kpi_resolved.metric("Resolved", f"{is_resolved.mean() * 100:.0f}%")
kpi_median.metric("Median resolution (hrs)", f"{filtered_tickets['resolution_hours'].median():.1f}")
kpi_reopen.metric("Reopen rate", f"{(filtered_tickets['Reopen Count'] > 0).mean() * 100:.0f}%")

st.divider()

# 1. Recommendation
st.header("1. The recommendation")

scorecard = component_scorecard(filtered_tickets)
top_component = scorecard.index[0]
top_row = scorecard.loc[top_component]

# Justify the pick from the signals it actually leads on
reasons = []
if top_row["Reopen_pct"] == scorecard["Reopen_pct"].max() and top_row["Reopen_pct"] > 0:
    reasons.append(f"the highest reopen rate ({top_row['Reopen_pct']:.0f}%)")
if top_row["Tickets"] == scorecard["Tickets"].max():
    reasons.append(f"the highest ticket volume ({int(top_row['Tickets'])})")
if top_row["High_Critical_pct"] == scorecard["High_Critical_pct"].max() and top_row["High_Critical_pct"] > 0:
    reasons.append(f"the largest share of High/Critical tickets ({top_row['High_Critical_pct']:.0f}%)")

reason_text = "; ".join(reasons) if reasons else "the highest combined focus score"
st.success(
    f"**The data points to {top_component}.** It carries {reason_text}. "
    "Reopens are the strongest signal: they mean fixes there are not sticking, so "
    "investment compounds, because each properly fixed defect stops generating repeat work."
)

st.subheader("Investment priority by component")
st.caption(
    "Higher score means more worth investing in, so the longest bar is where to start. "
    "Volume, reopens, and severity are weighted equally; resolution speed is excluded."
)
ranked_components = scorecard.reset_index().sort_values("Focus_score")  # ascending -> top bar is largest
ranked_components["Label"] = ranked_components["Focus_score"].round().astype(int).astype(str)
fig = px.bar(
    ranked_components,
    x="Focus_score",
    y="Component",
    orientation="h",
    text="Label",
    color="Focus_score",
    color_continuous_scale="OrRd",
)
fig.update_traces(textposition="outside", cliponaxis=False)
fig.update_layout(coloraxis_showscale=False, xaxis_title="Focus score (0 to 100)", margin=dict(t=10))
st.plotly_chart(fig, use_container_width=True)

with st.expander("See the full breakdown (volume, reopens, severity)"):
    st.caption(
        "Further up and to the right means more tickets and more reopens; "
        "redder means a higher share of High/Critical tickets. That corner is where "
        "a quarter of investment pays off most."
    )
    breakdown = scorecard.reset_index()
    fig = px.scatter(
        breakdown,
        x="Tickets",
        y="Reopen_pct",
        color="High_Critical_pct",
        text="Component",
        color_continuous_scale="OrRd",
        labels={"Reopen_pct": "Reopen rate (%)", "High_Critical_pct": "High/Critical %"},
    )
    fig.update_traces(marker=dict(size=18), textposition="top center")
    fig.update_layout(margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# 2. The why
st.header("2. Why this component")
st.caption(
    f"The signals behind the ranking, one at a time. {top_component} stands out on the "
    "two that drive the score: ticket volume and reopen rate."
)

scorecard_labeled = scorecard.rename(
    columns={
        "High_Critical_pct": "High/Critical %",
        "Median_hrs": "Median hrs",
        "Reopen_pct": "Reopen %",
        "Avg_comments": "Avg comments",
        "Focus_score": "Focus score",
    }
)
scorecard_styled = (
    scorecard_labeled.style.format(
        {
            "High/Critical %": "{:.0f}%",
            "Median hrs": "{:.0f}",
            "Reopen %": "{:.0f}%",
            "Avg comments": "{:.1f}",
            "Focus score": "{:.0f}",
        }
    )
    .background_gradient(cmap="Reds", subset=["Tickets", "High/Critical %", "Median hrs", "Reopen %"])
    .background_gradient(cmap="Oranges", subset=["Focus score"])
)
with st.expander("See the full scorecard numbers"):
    st.dataframe(scorecard_styled, use_container_width=True)

volume_col, reopen_col = st.columns(2)
with volume_col:
    st.subheader("Ticket volume by component")
    volume_by_component = filtered_tickets["Component"].value_counts().reset_index()
    volume_by_component.columns = ["Component", "Tickets"]
    fig = px.bar(volume_by_component, x="Tickets", y="Component", orientation="h")
    fig.update_layout(yaxis=dict(autorange="reversed"), margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

with reopen_col:
    st.subheader("Reopen rate by component")
    reopen_rates = reopen_by_component(filtered_tickets)
    reopen_rates["Label"] = reopen_rates["Reopen %"].round().astype(int).astype(str) + "%"
    fig = px.bar(
        reopen_rates,
        x="Reopen %",
        y="Component",
        orientation="h",
        text="Label",
        color="Reopen %",
        color_continuous_scale="Reds",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(coloraxis_showscale=False, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

st.subheader(f"What to fix first in {top_component}")
st.caption(
    "Recurring Reported Issues ranked by pain score (0 to 100): volume, severity (% High/"
    "Critical), and reopen rate, each min-max normalized across all recurring issues and "
    "averaged. Reported Issues with at least 8 tickets. The number in parentheses is the "
    "ticket count for that issue."
)
pain_table = pain_score_table(filtered_tickets)
pain_families = pain_table[pain_table["Component"] == top_component].head(10)
if pain_families.empty:
    st.info("No recurring Reported Issues (8+ tickets) for this component in the current selection.")
else:
    pain_families = pain_families.assign(
        IssueLabel=pain_families["Issue"] + " (" + pain_families["Tickets"].astype(str) + ")"
    )
    fig = px.bar(
        pain_families,
        x="Pain score",
        y="IssueLabel",
        orientation="h",
        text="Pain score",
        color="Pain score",
        color_continuous_scale="OrRd",
        custom_data=["Tickets", "High/Critical %", "Reopen %"],
    )
    fig.update_traces(
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>Pain score: %{x}<br>Tickets: %{customdata[0]}"
            "<br>High/Critical: %{customdata[1]}%<br>Reopen: %{customdata[2]}%<extra></extra>"
        ),
    )
    fig.update_layout(
        yaxis=dict(autorange="reversed", title=None),
        coloraxis_showscale=False,
        margin=dict(t=10),
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# 3. Release of product
st.header("3. The Oct 1 release")
st.caption("Whether the major release on Oct 1, 2025 made things worse, and for which component.")

st.subheader("Tickets created over time")
monthly_volume = filtered_tickets.groupby("created_month").size().reset_index(name="Tickets")
monthly_volume["month_start"] = pd.to_datetime(monthly_volume["created_month"])
fig = px.line(monthly_volume, x="month_start", y="Tickets", markers=True)
fig.add_vline(
    x=RELEASE_DATE.isoformat(),
    line_dash="dash",
    line_color="crimson",
    annotation_text="Major release, Oct 1, 2025",
    annotation_position="top left",
)
fig.update_layout(xaxis_title="Month", margin=dict(t=10))
st.plotly_chart(fig, use_container_width=True)

st.subheader("Open backlog over time")
st.caption(
    "Is the team keeping up? The line is the running open backlog (tickets created so far minus "
    "resolved so far). A steadily rising line means more is coming in than going out, so the team "
    "falls behind even when per-ticket resolution speed holds steady."
)
if filtered_tickets.empty:
    st.info("No tickets in the current selection.")
else:
    created_per_month = (
        filtered_tickets.groupby(filtered_tickets["Created"].dt.to_period("M")).size().rename("created")
    )
    resolved_tickets = filtered_tickets[filtered_tickets["Resolved"].notna()]
    resolved_per_month = (
        resolved_tickets.groupby(resolved_tickets["Resolved"].dt.to_period("M")).size().rename("resolved")
    )
    monthly_flow = pd.concat([created_per_month, resolved_per_month], axis=1).fillna(0).sort_index()
    monthly_flow["backlog"] = (monthly_flow["created"] - monthly_flow["resolved"]).cumsum()
    monthly_flow.index = monthly_flow.index.to_timestamp()
    monthly_flow = monthly_flow.rename_axis("month_start").reset_index()
    fig = px.line(monthly_flow, x="month_start", y="backlog", markers=True)
    fig.update_traces(line_color="indianred")
    fig.add_vline(
        x=RELEASE_DATE.isoformat(),
        line_dash="dash",
        line_color="crimson",
        annotation_text="Major release, Oct 1, 2025",
        annotation_position="top left",
    )
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Open tickets (cumulative)",
        margin=dict(t=10),
    )
    st.plotly_chart(fig, use_container_width=True)

before_release = filtered_tickets[filtered_tickets["post_release"].eq(False)]
after_release = filtered_tickets[filtered_tickets["post_release"]]

if before_release.empty or after_release.empty:
    st.info(
        "Select a date range (and statuses) that spans both sides of "
        "Oct 1, 2025 to compare before and after the release."
    )
else:
    def reopen_rate(tickets: pd.DataFrame) -> float:
        return (tickets["Reopen Count"] > 0).mean() * 100

    def high_priority_share(tickets: pd.DataFrame) -> float:
        return tickets["Priority"].isin(HIGH_PRIORITIES).mean() * 100

    metric_reopen, metric_resolution, metric_severity = st.columns(3)
    metric_reopen.metric(
        "Reopen rate",
        f"{reopen_rate(after_release):.0f}%",
        delta=f"{reopen_rate(after_release) - reopen_rate(before_release):+.1f} pts",
        delta_color="inverse",
    )
    metric_resolution.metric(
        "Median resolution (hrs)",
        f"{after_release['resolution_hours'].median():.0f}",
        delta=f"{after_release['resolution_hours'].median() - before_release['resolution_hours'].median():+.1f}",
        delta_color="inverse",
    )
    metric_severity.metric(
        "High/Critical share",
        f"{high_priority_share(after_release):.0f}%",
        delta=f"{high_priority_share(after_release) - high_priority_share(before_release):+.1f} pts",
        delta_color="inverse",
    )
    st.caption("Values are post-release; deltas compare against pre-release. Red means it got worse.")

    # Incoming volume per component, before vs. after
    # Normalized to tickets-per-month because two windows differ in length (9 months before, 8 after)
    before_months = max(before_release["created_month"].nunique(), 1)
    after_months = max(after_release["created_month"].nunique(), 1)
    volume_by_period = (
        filtered_tickets.assign(Period=filtered_tickets["post_release"].map({False: "Before", True: "After"}))
        .groupby(["Component", "Period"])
        .size()
        .reset_index(name="Tickets")
    )
    volume_by_period["Per month"] = volume_by_period["Tickets"] / volume_by_period["Period"].map(
        {"Before": before_months, "After": after_months}
    )
    st.subheader("Incoming volume by component, before vs. after release")
    st.caption(
        f"Tickets per month, normalized because the before window is {before_months} months "
        f"and the after window is {after_months}. A taller After bar means more incoming volume."
    )
    fig = px.bar(
        volume_by_period,
        x="Component",
        y="Per month",
        color="Period",
        barmode="group",
        category_orders={"Period": ["Before", "After"]},
        color_discrete_map={"Before": "#9ecae1", "After": "#fb6a4a"},
        labels={"Per month": "Tickets per month"},
    )
    fig.update_layout(margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    volume_pivot = volume_by_period.pivot(index="Component", columns="Period", values="Per month")
    if {"Before", "After"}.issubset(volume_pivot.columns):
        volume_pivot["delta"] = volume_pivot["After"] - volume_pivot["Before"]
        top_volume_riser = volume_pivot["delta"].idxmax()
        before_per_month = volume_pivot.loc[top_volume_riser, "Before"]
        after_per_month = volume_pivot.loc[top_volume_riser, "After"]
        pct_change_text = f", +{(after_per_month / before_per_month - 1) * 100:.0f}%" if before_per_month > 0 else ""
        st.markdown(
            f"Incoming volume rose across the board after the release, and **{top_volume_riser}** climbed most "
            f"(**{before_per_month:.1f} to {after_per_month:.1f} tickets per month{pct_change_text}**). "
            f"Volume alone points at {top_volume_riser}, "
            f"but the reopen view below is what isolates {top_component} as the quality problem."
        )

    reopen_by_period = (
        filtered_tickets.assign(
            is_reopened=filtered_tickets["Reopen Count"] > 0,
            Period=filtered_tickets["post_release"].map({False: "Before", True: "After"}),
        )
        .groupby(["Component", "Period"])["is_reopened"]
        .mean()
        .mul(100)
        .reset_index(name="Reopen %")
    )
    st.subheader("Reopen rate by component, before vs. after release")
    fig = px.bar(
        reopen_by_period,
        x="Component",
        y="Reopen %",
        color="Period",
        barmode="group",
        category_orders={"Period": ["Before", "After"]},
        color_discrete_map={"Before": "#9ecae1", "After": "#fb6a4a"},
    )
    fig.update_layout(margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

    reopen_pivot = reopen_by_period.pivot(index="Component", columns="Period", values="Reopen %")
    if {"Before", "After"}.issubset(reopen_pivot.columns):
        reopen_pivot["delta"] = reopen_pivot["After"] - reopen_pivot["Before"]
        top_reopen_riser = reopen_pivot["delta"].idxmax()
        st.markdown(
            f"After the release, **{top_reopen_riser}** saw the largest reopen-rate jump "
            f"(**{reopen_pivot.loc[top_reopen_riser, 'Before']:.0f}% to "
            f"{reopen_pivot.loc[top_reopen_riser, 'After']:.0f}%**), "
            "the clearest evidence tying the release to where the team should invest."
        )

st.divider()

# 4. More context
st.header("4. Operational context")
st.caption("Broader background. Useful to know, but not specific to the where-to-invest decision.")

st.subheader("Open backlog by component")
st.caption("Unresolved tickets right now. Where work is piling up today.")
open_tickets = filtered_tickets[filtered_tickets["Status"].ne("Resolved")]
if open_tickets.empty:
    st.info("No open tickets in the current selection.")
else:
    open_by_component = open_tickets["Component"].value_counts().sort_values().reset_index()
    open_by_component.columns = ["Component", "Open tickets"]
    fig = px.bar(
        open_by_component,
        x="Open tickets",
        y="Component",
        orientation="h",
        text="Open tickets",
        color="Open tickets",
        color_continuous_scale="Blues",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig.update_layout(coloraxis_showscale=False, margin=dict(t=10))
    st.plotly_chart(fig, use_container_width=True)

with st.expander("Workload by assignee and type of work"):
    st.caption("Bar height is total tickets; segments show the mix of work each person handled.")
    workload_by_assignee = filtered_tickets.groupby(["Assignee", "Issue Type"]).size().reset_index(name="Tickets")
    assignee_order = filtered_tickets["Assignee"].value_counts().index.tolist()
    fig = px.bar(
        workload_by_assignee,
        x="Assignee",
        y="Tickets",
        color="Issue Type",
        category_orders={"Assignee": assignee_order},
    )
    fig.update_layout(margin=dict(t=10), legend_title_text="Type of work")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# 5. Explore tickets
st.header("5. Explore the tickets")
st.caption("The filtered rows behind every chart above. Search, browse, or download.")
search_term = st.text_input("Search summaries", placeholder="e.g. refund, login, timeout")
visible_tickets = filtered_tickets
if search_term:
    visible_tickets = visible_tickets[
        visible_tickets["Summary"].str.contains(search_term, case=False, na=False)
    ]

st.dataframe(visible_tickets[ORIGINAL_COLUMNS], use_container_width=True, hide_index=True)
st.caption("Original source columns only; the derived analysis fields are hidden here and in the download.")
st.download_button(
    "Download filtered tickets (CSV)",
    data=visible_tickets[ORIGINAL_COLUMNS].to_csv(index=False).encode("utf-8"),
    file_name="tickets_filtered.csv",
    mime="text/csv",
)
