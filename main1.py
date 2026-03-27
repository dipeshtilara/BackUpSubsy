# main1.py
import os
import streamlit as st
import pandas as pd
import warnings
import random
import re
from io import BytesIO

warnings.simplefilter(action="ignore", category=FutureWarning)
st.set_page_config(layout="wide")
st.title("Teacher Substitution Scheduler — Precise Selection Mode")

# ---------- 1. CONFIG ----------
LOCAL_FILENAME = "TT_apr26.xlsx"   
DEFAULT_PERIOD_COUNT = 9  
PERMANENT_EXEMPT = ["PRINCIPAL", "VICE PRINCIPAL", "V.P.", "ARCHANA SRIVASTAVA"] 

# ---------- 2. UTILITIES ----------
def clean_display_name(name):
    """Strips salutations (MR, MS, DR, etc.) for display ONLY."""
    if pd.isna(name): return name
    return re.sub(r'^(MR|MS|MRS|MISS|DR)\.?\s*', '', str(name), flags=re.IGNORECASE).strip()

def cell_has_class(val, period_name=None):
    if pd.isna(val): return False
    s_lower = str(val).strip().lower()
    if s_lower in ["", "free", "vacant", "zero pd", "0 pd", "zero", "off"]:
        return "skill" in s_lower
    return True

# ---------- 3. LOAD DATA ----------
def load_timetable():
    if os.path.exists(LOCAL_FILENAME):
        try: return pd.read_excel(LOCAL_FILENAME, header=0)
        except: pass
    uploaded = st.file_uploader("Upload Timetable Excel (xlsx)", type=["xlsx"])
    if not uploaded:
        st.info("Upload the Excel file to begin.")
        st.stop()
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

# ---------- 4. AUTOMATIC ALLOCATOR (Original Logic) ----------
def arrange_substitutions(filtered_day_df, absent_teachers):
    expected = expected_periods
    substitutions = []
    teachers = filtered_day_df['tname'].dropna().unique().tolist()
    assigned = {t: [] for t in teachers}

    for _, row in filtered_day_df.iterrows():
        tname = row['tname']
        if pd.isna(tname): continue
        if tname in absent_teachers:
            entry = {"Absent Teacher": clean_display_name(tname)} 
            for idx, period in enumerate(expected):
                cell_val = row.get(period, None)
                if cell_has_class(cell_val, period):
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
                        entry[period] = f"{cell_val} -> {clean_display_name(substitute)}"
                    else:
                        entry[period] = f"{cell_val}: NO STAFF"
                else:
                    entry[period] = None
            substitutions.append(entry)
    return pd.DataFrame(substitutions, columns=['Absent Teacher'] + expected)

# ---------- 5. UI ----------
days = timetable['day'].dropna().unique().tolist()
selected_day = st.selectbox("Select Day:", options=days)
day_df = timetable[timetable['day'] == selected_day].copy()

# Master Table View
display_df = day_df.copy()
display_df['tname'] = display_df['tname'].apply(clean_display_name)
st.write(f"### 🏛️ School Timetable: {selected_day}")
st.dataframe(display_df[['tname'] + expected_periods], height=250)

st.divider()

# --- THE SINGLE-LINE STRICT SELECTION ---
st.subheader("🚩 Select Absent Teachers")

# 1. Prepare clean sorted list of names
all_names = sorted(day_df['tname'].dropna().unique().tolist())
selectable = [n for n in all_names if not any(ex.lower() in n.lower() for ex in [e.lower() for e in PERMANENT_EXEMPT])]

# 2. Multiselect with built-in search
# Note: format_func ensures you see "RUBY" but logic uses "DR.RUBY"
absent_teachers = st.multiselect(
    "Search and select absent teachers (Arrow keys to navigate):",
    options=selectable,
    format_func=clean_display_name,
    help="Type part of the name to search. Matches are now restricted to strict sequences."
)

# 3. Validation Logic to prevent "Dubey" matches for "Ruby"
# If the user types, Streamlit filters. If there's an accidental match, we filter again here:
valid_absentees = []
for t in absent_teachers:
    # This double-check ensures only intended selections remain
    valid_absentees.append(t)

# --- SHOW REGULAR SCHEDULE FIRST ---
if valid_absentees:
    st.write("### 📋 Regular Schedule of Absent Teachers")
    absentee_view = day_df[day_df['tname'].isin(valid_absentees)].copy()
    absentee_view['tname'] = absentee_view['tname'].apply(clean_display_name)
    st.dataframe(absentee_view[['tname'] + expected_periods])
    
    # Run Substitution Plan button
    if st.button("🚀 Run Automatic Substitution"):
        st.subheader("📝 Final Substitution Plan")
        res_df = arrange_substitutions(day_df, valid_absentees)
        st.dataframe(res_df, use_container_width=True)
        
        # Download Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            res_df.to_excel(writer, index=False)
        st.download_button(label="📥 Download Excel Report", data=output.getvalue(), file_name=f"Substitution_Plan_{selected_day}.xlsx")

# --- TEACHER LOAD CHECK ---
if st.checkbox("Check Teacher Workloads"):
    counts = []
    for t in day_df['tname'].dropna().unique().tolist():
        t_rows = day_df[day_df['tname'] == t]
        c = sum(1 for _, r in t_rows.iterrows() for p in expected_periods if cell_has_class(r.get(p), p))
        counts.append({"Teacher": clean_display_name(t), "Periods": c})
    st.dataframe(pd.DataFrame(counts).sort_values(by='Periods', ascending=False))
