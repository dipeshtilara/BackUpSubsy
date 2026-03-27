# main1.py
import os
import streamlit as st
import pandas as pd
import warnings
import random
import re

warnings.simplefilter(action="ignore", category=FutureWarning)
st.set_page_config(layout="wide")
st.title("Teacher Substitution Scheduler — Precise Selection Mode")

# ---------- CONFIG ----------
LOCAL_FILENAME = "TT_apr26.xlsx"   
DEFAULT_PERIOD_COUNT = 9  
PERMANENT_EXEMPT = ["PRINCIPAL", "VICE PRINCIPAL", "V.P.", "ARCHANA SRIVASTAVA"] 

# ---------- THE NAME CLEANER (Stripping MR. MS. etc) ----------
def clean_display_name(name):
    """Removes MR. MS. MRS. etc. from the string for display/output."""
    if pd.isna(name): return name
    # Strips MR/MS/MRS/MISS regardless of dots or spaces
    return re.sub(r'^(MR|MS|MRS|MISS)\.?\s*', '', str(name), flags=re.IGNORECASE).strip()

# ---------- LOAD FILE ----------
def load_timetable():
    if os.path.exists(LOCAL_FILENAME):
        try:
            return pd.read_excel(LOCAL_FILENAME, header=0)
        except: pass
    uploaded = st.file_uploader("Upload timetable Excel", type=["xlsx"])
    if not uploaded: st.stop()
    return pd.read_excel(uploaded, header=0)

timetable = load_timetable()
timetable.columns = timetable.columns.str.strip().str.lower()

day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
timetable['day'] = timetable['day'].str.strip().str.capitalize()
timetable['day'] = pd.Categorical(timetable['day'], categories=day_order, ordered=True)

import re
cols = list(timetable.columns)
period_cols = [c for c in cols if re.fullmatch(r'p\d+', c)]
expected_periods = sorted(period_cols, key=lambda x: int(re.findall(r'\d+', x)[0]))

# ---------- Helper: determine whether cell counts as class ----------
def cell_has_class(val, period_name=None):
    if pd.isna(val): return False
    s_lower = str(val).strip().lower()
    if s_lower in ["", "free", "vacant", "zero pd", "0 pd", "zero", "off"]:
        return "skill" in s_lower
    return True

# ---------- Automatic Substitution Allocator (Your Logic) ----------
def arrange_substitutions(filtered_day_df, absent_teachers):
    expected = expected_periods
    substitutions = []
    
    teachers = filtered_day_df['tname'].dropna().unique().tolist()
    assigned = {t: [] for t in teachers}

    for _, row in filtered_day_df.iterrows():
        tname = row['tname']
        if pd.isna(tname): continue
        
        # Internal matching for absentees
        if tname in absent_teachers:
            # Output uses cleaned name
            entry = {"tname": clean_display_name(tname)} 
            
            for period in expected:
                if cell_has_class(row.get(period, None), period):
                    free_teachers = filtered_day_df[
                        ((filtered_day_df[period].isna()) | (filtered_day_df[period].astype(str).str.strip() == "")) &
                        (~filtered_day_df['tname'].isin(absent_teachers)) &
                        (~filtered_day_df['tname'].str.upper().isin([ex.upper() for ex in PERMANENT_EXEMPT]))
                    ]['tname'].dropna().unique().tolist()
                    
                    random.shuffle(free_teachers)
                    substitute = None
                    for cand in free_teachers:
                        first_half = any(p in assigned.get(cand, []) for p in expected[:5])
                        second_half = any(p in assigned.get(cand, []) for p in expected[5:])
                        if period in expected[:5] and first_half: continue
                        if period in expected[5:] and second_half: continue
                        
                        substitute = cand
                        assigned.setdefault(cand, []).append(period)
                        break
                    
                    if substitute:
                        entry[period] = f"{row.get(period)} -> {clean_display_name(substitute)}"
                    else:
                        entry[period] = f"{row.get(period)}: NO STAFF"
                else:
                    entry[period] = None
            substitutions.append(entry)
            
    return pd.DataFrame(substitutions, columns=['tname'] + expected)

# ---------- UI ----------
view_mode = st.radio("Select view mode:", ["Daily", "Weekly"], horizontal=True)

if view_mode == "Daily":
    days = timetable['day'].dropna().unique().tolist()
    selected_day = st.selectbox("Select day:", options=days)
    day_df = timetable[timetable['day'] == selected_day].copy()
    
    # 1. Master view with clean names
    display_table = day_df.copy()
    display_table['tname'] = display_table['tname'].apply(clean_display_name)
    st.write(f"### Master Timetable for {selected_day}")
    st.dataframe(display_table)

    # 2. Precise Selection List
    # We sort the list alphabetically to make arrow-key navigation easier
    all_names = sorted(day_df['tname'].dropna().unique().tolist())
    selectable = [n for n in all_names if not any(ex.lower() in n.lower() for ex in PERMANENT_EXEMPT)]
    
    st.info("💡 Use Arrow Keys to navigate and Enter to select teachers from the list below.")
    absent_teachers = st.multiselect(
        "Select absent teachers:", 
        options=selectable, 
        format_func=clean_display_name, # Shows clean name but keeps full name for matching
        help="Scroll or use arrow keys to pick specific names."
    )

    if absent_teachers:
        if st.button("🚀 Run Automatic Substitution"):
            subs = arrange_substitutions(day_df, absent_teachers)
            st.write("### Proposed Substitution Schedule")
            st.dataframe(subs)

    if st.checkbox("Show period counts"):
        counts = []
        for t in day_df['tname'].dropna().unique().tolist():
            t_rows = day_df[day_df['tname'] == t]
            c = sum(1 for _, r in t_rows.iterrows() for p in expected_periods if cell_has_class(r.get(p), p))
            counts.append({"Teacher": clean_display_name(t), "Periods": c})
        st.dataframe(pd.DataFrame(counts).sort_values(by='Periods', ascending=False))
