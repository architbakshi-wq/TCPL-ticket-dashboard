# app.py - TCPL Ticket Dashboard (SLA/Shift colors + shortened TicketType labels)
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO
import os

# ------------------- App configuration ------------------------------------
st.set_page_config(page_title="TCPL Ticket Dashboard", layout="wide", initial_sidebar_state="collapsed")

# Custom styles for deeper colors and nicer look
st.markdown(
    """
    <style>
    .reportview-container .main .block-container{padding-top:1rem;}
    h1 {color: #0b3954; font-weight:700;}
    .metric-label {color: #3a3a3a;}
    .stButton>button {background-color:#0b3954;color:white;border-radius:6px;}
    </style>
    """, unsafe_allow_html=True
)

# ------------------- Header ------------------------------------------------
st.title("📊 TCPL Ticket Management Dashboard")
st.markdown("Upload or place `data.xlsx` in the app repository. Use the filters on top to refine the view.")

# ------------------- Data loading -----------------------------------------
uploaded_file = st.file_uploader("Upload Excel File (.xlsx)", type=["xlsx"], help="Drag & drop or browse. SP can upload weekly/monthly files here.")

# If no upload, try repository default file
DEFAULT_DATAFILE = "data.xlsx"
if uploaded_file is None and os.path.exists(DEFAULT_DATAFILE):
    uploaded_file = DEFAULT_DATAFILE

if not uploaded_file:
    st.info("No data file found. Upload an Excel file or add a file named `data.xlsx` to the repository.")
    st.stop()

# Read excel
try:
    df = pd.read_excel(uploaded_file)
except Exception as e:
    st.error(f"Could not read the uploaded file: {e}")
    st.stop()

# Basic cleaning and normalizing column names
df.columns = [c.strip() for c in df.columns]

# Parse dates
for col in ["Created Time", "Closed Time"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")

# Derived fields
if "Created Time" in df.columns:
    df["Created Date"] = df["Created Time"].dt.date
    df["Created Month"] = df["Created Time"].dt.to_period("M").astype(str)

if ("Created Time" in df.columns) and ("Closed Time" in df.columns):
    df["Resolution (hrs)"] = (df["Closed Time"] - df["Created Time"]).dt.total_seconds() / 3600.0
else:
    df["Resolution (hrs)"] = np.nan

# Ensure string columns exist to avoid key errors
for col in ["Priority", "TicketType", "Resolution Status", "Shift Timing", "Status"]:
    if col not in df.columns:
        df[col] = np.nan
    df[col] = df[col].astype(str).fillna("")

# ------------------- Shorten TicketType labels (Option A) -----------------
tickettype_map = {
    "Configuration & Master Update (Non-Tech)": "Config & Master",
    "Bug (Tech)": "Bug (Tech)",
    "Data Correction (Tech)": "Data Correction",
    "Not a Task (Info Only)": "Info Only"
}
df["TicketTypeShort"] = df["TicketType"].map(tickettype_map).fillna(df["TicketType"])

# ------------------- Top Filters ------------------------------------------
with st.container():
    cols = st.columns([1.2,1.2,1,1,1,1])

    with cols[0]:
        priority_opts = sorted([p for p in df["Priority"].unique() if p and p.lower()!="nan"])
        priorities = st.multiselect("Priority", options=priority_opts, default=priority_opts)

    with cols[1]:
        type_opts = sorted([t for t in df["TicketTypeShort"].unique() if t and str(t).lower()!="nan"])
        tt = st.multiselect("Ticket Type", options=type_opts, default=type_opts)

    with cols[2]:
        sla_opts = sorted([s for s in df["Resolution Status"].unique() if s and s.lower()!="nan"])
        sla = st.multiselect("SLA Status", options=sla_opts, default=sla_opts)

    with cols[3]:
        status_opts = sorted([s for s in df["Status"].unique() if s and s.lower()!="nan"])
        status_sel = st.multiselect("Ticket Status", options=status_opts, default=status_opts)

    with cols[4]:
        shift_opts = sorted([s for s in df["Shift Timing"].unique() if s and s.lower()!="nan"])
        shifts = st.multiselect("Shift Timing", options=shift_opts, default=shift_opts)

    with cols[5]:
        if "Created Time" in df.columns:
            min_date = df["Created Time"].min().date()
            max_date = df["Created Time"].max().date()
            daterange = st.date_input("Created Date range", [min_date, max_date])
        else:
            daterange = None

# Fix single-date selection
start_date = end_date = None
if daterange:
    if isinstance(daterange, list) and len(daterange) == 2:
        start_date, end_date = daterange
    elif isinstance(daterange, list) and len(daterange) == 1:
        start_date = end_date = daterange[0]
    else:
        start_date = end_date = daterange

if start_date:
    start_date = pd.to_datetime(start_date)
if end_date:
    end_date = pd.to_datetime(end_date)

# ------------------- Apply filters ----------------------------------------
filtered = df.copy()

if priorities:
    filtered = filtered[filtered["Priority"].isin(priorities)]

if tt:
    filtered = filtered[filtered["TicketTypeShort"].isin(tt)]

if sla:
    filtered = filtered[filtered["Resolution Status"].isin(sla)]

if status_sel:
    filtered = filtered[filtered["Status"].isin(status_sel)]

if shifts:
    filtered = filtered[filtered["Shift Timing"].isin(shifts)]

  # --- Robust date filtering (replace existing date filter) ---
if start_date is not None and 'Created Time' in filtered.columns:
    try:
        # Ensure start_date and end_date are single pandas Timestamps (scalars)
        sd = pd.to_datetime(start_date)
        ed = pd.to_datetime(end_date) if end_date is not None else sd

        # If either conversion produced PeriodIndex/array, take first element
        if hasattr(sd, "__len__") and not isinstance(sd, pd.Timestamp):
            sd = pd.to_datetime(sd[0])
        if hasattr(ed, "__len__") and not isinstance(ed, pd.Timestamp):
            ed = pd.to_datetime(ed[0])

        # Use between() which is safe and clear
        filtered = filtered[filtered['Created Time'].between(sd, ed)]
    except Exception as e:
        st.error(f"Date filter failed, skipping date filter: {e}")


# ------------------- KPIs --------------------------------------------------
total = len(filtered)
within_sla_count = int(filtered["Resolution Status"].str.contains("Within", case=False, na=False).sum())
sla_pct = round((within_sla_count/total*100),2) if total else 0
avg_res_hrs = round(filtered["Resolution (hrs)"].mean(),2) if not filtered["Resolution (hrs)"].isna().all() else None
bug_count = int(filtered[filtered["TicketType"].str.contains("bug", case=False, na=False)].shape[0])
p4_count = int(filtered[filtered["Priority"]=="P4"].shape[0])

k1,k2,k3,k4,k5 = st.columns([1.2,1,1,1,1])
k1.metric("Total Tickets", total)
k2.metric("Within SLA", f"{within_sla_count} ({sla_pct}%)")
k3.metric("Avg Resolution (hrs)", avg_res_hrs if avg_res_hrs is not None else "—")
k4.metric("Bug Tickets", bug_count)
k5.metric("P4 Tickets", p4_count)

st.markdown("---")

# ------------------- Charts ------------------------------------------------
chart_col1, chart_col2 = st.columns([2,2])

sla_colors = {"Within SLA": "#0FA958", "SLA Violated": "#E02020"}
shift_colors = {"Within Shift": "#007BFF", "After Shift": "#FF8C00"}

with chart_col1:
    st.subheader("SLA Adherence")
    if not filtered.empty:
        sla_df = filtered["Resolution Status"].value_counts().rename_axis("SLA").reset_index(name="count")
        fig_sla = px.pie(
            sla_df, names="SLA", values="count", hole=0.35,
            color_discrete_map=sla_colors
        )
        fig_sla.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig_sla, use_container_width=True)

with chart_col2:
    st.subheader("Tickets by Type and Shift")
    cross = filtered.groupby(["TicketTypeShort","Shift Timing"]).size().reset_index(name="count")
    if not cross.empty:
        fig_bar = px.bar(
            cross, x="TicketTypeShort", y="count", color="Shift Timing",
            barmode="group", text="count", color_discrete_map=shift_colors
        )
        fig_bar.update_layout(
            xaxis_tickangle=0,
            xaxis_tickfont=dict(size=11),
            margin=dict(l=40, r=20, t=50, b=120)
        )
        st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")

# ------------------- Lower Charts ----------------------------------------
c1,c2 = st.columns(2)

with c1:
    st.subheader("Tickets by Priority")
    pr = filtered["Priority"].value_counts().reset_index()
    pr.columns = ["Priority","count"]
    fig_pr = px.bar(
        pr, x="Priority", y="count", text="count",
        color="Priority", color_discrete_sequence=px.colors.qualitative.Set2
    )
    st.plotly_chart(fig_pr, use_container_width=True)

with c2:
    st.subheader("Ticket Type Distribution")
    fig_p = px.pie(filtered, names="TicketTypeShort", hole=0.3)
    st.plotly_chart(fig_p, use_container_width=True)

st.markdown("---")

# ------------------- Download Filtered Data -------------------------------
st.subheader("Filtered Tickets")
st.dataframe(filtered.reset_index(drop=True), height=350)

def to_excel_bytes(df_export):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="Filtered")
    return out.getvalue()

if not filtered.empty:
    st.download_button(
        "📥 Download filtered data",
        data=to_excel_bytes(filtered),
        file_name="filtered_tickets.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.caption("Designed for TCPL — deep colors, advanced filtering, and clear visual reporting.")
