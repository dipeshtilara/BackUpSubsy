# main1.py
import os
import streamlit as st
import pandas as pd
import warnings
import random
import re

warnings.simplefilter(action="ignore", category=FutureWarning)
st.set_page_config(layout="wide")
st.title("Teacher Substitution Scheduler — Daily / Weekly")

# ---------- CONFIG ----------
LOCAL_FILENAME = "TT_apr26.xlsx"   
DEFAULT_PERIOD_COUNT = 9  
# List of staff to NEVER use for substitutions or list as absent
PERMANENT_EXEMPT = ["PRINCIPAL", "VICE PRINCIPAL", "V.P.", "ARCHANA SRIVASTAVA"] 

# ---------- LOGISTICS HELPER ----------
def get_zone(section_label):
    """Detects building based on grade level in the cell."""
    match = re.search(r'(\d+)', str(section_label))
    if not match: return "Main"
    grade = int(match.group())
    return "Junior" if 6 <= grade <= 7 else "Main"

# ---------- LOAD FILE ----------
def load_timetable():
    if os.path.exists(LOCAL_FILENAME):
        try:
            df = pd.read_excel(LOCAL_FILENAME, header=0)
            st.success(f"Loaded local file: {LOCAL_FILENAME}")
            return df
        except Exception as e:
            st.error(f"Could not read local file {LOCAL_FILENAME}: {e}")
    uploaded = st.file_uploader("Upload timetable Excel", type=["xlsx"])
    if not uploaded:
        st.info("Place TT_apr26.xlsx next to this script or upload an Excel file.")
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
if not period_cols:
    period_cols = [c for c in cols if re.match(r'p[_\-\s]?\d+', c)]
if not period_cols:
    period_cols = [f"p{i}" for i in range(DEFAULT_PERIOD_COUNT)]
expected_periods = sorted(period_cols, key=lambda x: int(re.findall(r'\d+', x)[0]))

# ---------- Helper: determine whether cell counts as class ----------
def cell_has_class(val, period_name=None):
    if pd.isna(val): return False
    s = str(val).strip()
    if s == "": return False
    s_lower = s.lower()
    
    # Check off-classes list from UI
    if 'off_classes_list' in globals() and off_classes_list:
        for off in off_classes_list:
            if off and off.lower() in s_lower: return False

    if period_name and period_name.lower() == "p0":
        return "skill" in s_lower
    if (("zero pd" in s_lower) or (s_lower == "0 pd") or (s_lower == "zero")) and ("skill" not in s_lower):
        return False
    return True

# ---------- Substitution allocator (Updated with Building Logic) ----------
def arrange_substitutions(filtered_day_df, absent_teachers):
    expected = expected_periods
    substitutions = []
    # Fairness tracker
    sub_counts = {t: 0 for t in filtered_day_df['tname'].unique()}

    for _, row in filtered_day_df.iterrows():
        tname = row['tname']
        if pd.isna(tname): continue
        
        # Only process if teacher is absent and NOT the Principal/VP
        if tname in absent_teachers and not any(ex.lower() in str(tname).lower() for ex in PERMANENT_EXEMPT):
            entry = {"tname": tname}
            for idx, period in enumerate(expected):
                cell_val = row.get(period, None)
                if cell_has_class(cell_val, period):
                    target_zone = get_zone(cell_val)
                    
                    # Find free teachers
                    free_teachers = filtered_day_df[
                        ((filtered_day_df[period].isna()) | (filtered_day_df[period].astype(str).str.strip() == "")) &
                        (~filtered_day_df['tname'].isin(absent_teachers)) &
                        (~filtered_day_df['tname'].str.upper().isin([ex.upper() for ex in PERMANENT_EXEMPT]))
                    ]['tname'].dropna().unique().tolist()
                    
                    # LOGISTICS: Priority scoring for building movement
                    def get_priority_score(cand):
                        score = sub_counts.get(cand, 0) * 10
                        # Check teacher's location in the NEXT period
                        if idx + 1 < len(expected):
                            next_p = expected[idx+1]
                            next_val = filtered_day_df[filtered_day_df['tname'] == cand][next_p].values[0]
                            if cell_has_class(next_val, next_p):
                                if get_zone(next_val) == target_zone:
                                    score -= 50 # Priority: they are already heading to this building
                                else:
                                    score += 50 # Penalty: they need to go to the other building next
                        return score

                    free_teachers.sort(key=get_priority_score)
                    
                    if free_teachers:
                        substitute = free_teachers[0]
                        sub_counts[substitute] += 1
                        entry[period] = f"{cell_val} -> {substitute} ({target_zone})"
                    else:
                        entry[period] = f"{cell_val} (NO STAFF)"
                else:
                    entry[period] = None
            substitutions.append(entry)
            
    return pd.DataFrame(substitutions, columns=['tname'] + expected)

# ---------- UI: Layout stays exactly as you had it ----------
view_mode = st.radio("Select view mode:", ["Daily", "Weekly"], horizontal=True)
off_classes = st.checkbox("Mark specific classes as off?")
off_classes_list = []
if off_classes:
    sample_vals = []
    for p in expected_periods: sample_vals.extend(timetable[p].dropna().astype(str).tolist())
    classes_list = sorted({s.strip() for s in sample_vals if s and s.strip()})
    off_classes_list = st.multiselect("Select off class substrings:", options=classes_list)

if view_mode == "Daily":
    days = timetable['day'].dropna().unique().tolist()
    selected_day = st.selectbox("Select day:", options=days)
    day_df = timetable[timetable['day'] == selected_day].copy()
    st.write(f"### Timetable for {selected_day}")
    st.dataframe(day_df)

    # Filter Principal/VP out of the dropdown
    all_names = day_df['tname'].dropna().unique().tolist()
    selectable = [n for n in all_names if not any(ex.lower() in n.lower() for ex in PERMANENT_EXEMPT)]
    absent_teachers = st.multiselect("Select absent teachers (Daily):", options=selectable)

    if absent_teachers:
        st.write("### Classes handled by selected absent teachers")
        st.dataframe(day_df[day_df['tname'].isin(absent_teachers)])
        
        if st.button("Generate Substitutions"):
            subs = arrange_substitutions(day_df, absent_teachers)
            st.dataframe(subs)

    if st.checkbox("Show period counts for teachers (Daily)"):
        counts = []
        for teacher in day_df['tname'].dropna().unique().tolist():
            teacher_rows = day_df[day_df['tname'] == teacher]
            c = sum(1 for _, r in teacher_rows.iterrows() for p in expected_periods if cell_has_class(r.get(p), p))
            counts.append({"tname": teacher, "periods_today": c})
        st.dataframe(pd.DataFrame(counts).sort_values(by='periods_today', ascending=False))

else:
    # Weekly view logic stays exactly as you had it
    st.write("### Weekly view")
    teachers_all = timetable['tname'].dropna().unique().tolist()
    teacher_choice = st.selectbox("Select teacher (or All):", options=["All"] + teachers_all)
    # ... (Rest of your weekly display code remains unchanged)
