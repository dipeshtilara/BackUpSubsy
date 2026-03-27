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
st.title("Teacher Substitution Scheduler — Salutation-Aware Mode")

# ---------- 1. CONFIG ----------
LOCAL_FILENAME = "TT_apr26.xlsx"   
# Use the same casing as your Excel here
PERMANENT_EXEMPT = ["PRINCIPAL", "VICE PRINCIPAL", "V.P.", "ARCHANA SRIVASTAVA"] 

# ---------- 2. UTILITIES ----------
def get_zone(section_label):
    match = re.search(r'(\d+)', str(section_label))
    if not match: return "Main"
    grade = int(match.group())
    return "Junior" if 6 <= grade <= 7 else "Main"

def cell_has_class(val):
    """
    Directly adapted from your older logic:
    Checks for 'zero', 'off', 'vacant', etc., while ignoring 'skill'.
    """
    if pd.isna(val): return False
    s_lower = str(val).strip().lower()
    if s_lower in ["", "free", "vacant", "zero pd", "0 pd", "zero", "off"]:
        return "skill" in s_lower # True only if it's a skill period
    return True

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Substitutions')
    return output.getvalue()

# ---------- 3. LOAD DATA ----------
def load_timetable():
    if os.path.exists(LOCAL_FILENAME):
        try: return pd.read_excel(LOCAL_FILENAME, header=0)
        except: pass
    uploaded = st.file_uploader("Upload Excel", type=["xlsx"])
    if not uploaded: st.stop()
    return pd.read_excel(uploaded, header=0)

timetable = load_timetable()
timetable.columns = timetable.columns.str.strip().str.lower()
period_cols = sorted([c for c in timetable.columns if re.fullmatch(r'p\d+', c)], key=lambda x: int(re.findall(r'\d+', x)[0]))

# ---------- 4. THE ENGINE (Salutation-Aware Logic) ----------
def arrange_substitutions(day_df, absent_teachers):
    results = []
    sub_counts = {}

    # Standardize exempt list for substring checking
    exempt_list = [n.lower() for n in PERMANENT_EXEMPT]

    for _, row in day_df.iterrows():
        tname = str(row['tname']).strip()
        tname_lower = tname.lower()

        # Check if this teacher is absent or exempt (Substring Match)
        is_absent = any(abs_t.lower() in tname_lower for abs_t in absent_teachers)
        is_exempt = any(ex.lower() in tname_lower for ex in exempt_list)

        if is_absent and not is_exempt:
            entry = {"Absent Teacher": tname}
            
            for idx, p_col in enumerate(period_cols):
                val = row.get(p_col)
                if cell_has_class(val):
                    target_zone = get_zone(val)
                    
                    # Find free teachers using the 'cell_has_class' check on each period
                    # This naturally ignores salutations because it looks at the CLASS cells, not names
                    free_mask = day_df[p_col].apply(lambda x: not cell_has_class(x))
                    
                    # Filter out those who are absent or exempt
                    # We check if the name in the row contains any of our 'blocked' strings
                    not_blocked = day_df['tname'].apply(lambda x: 
                        not any(abs_t.lower() in str(x).lower() for abs_t in absent_teachers) and 
                        not any(ex.lower() in str(x).lower() for ex in exempt_list)
                    )
                    
                    free_teachers = day_df[free_mask & not_blocked]['tname'].unique().tolist()
                    
                    # Priority Scoring (Fairness + Building Travel)
                    def get_priority_score(t):
                        score = sub_counts.get(t, 0) * 10
                        # Travel Logic: Check if their next class is in the same zone
                        if idx + 1 < len(period_cols):
                            teacher_row = day_df[day_df['tname'] == t]
                            if not teacher_row.empty:
                                next_val = teacher_row[period_cols[idx+1]].values[0]
                                if cell_has_class(next_val) and get_zone(next_val) == target_zone:
                                    score -= 50
                        return score

                    free_teachers.sort(key=get_priority_score)
                    
                    if free_teachers:
                        sub = free_teachers[0]
                        entry[p_col] = f"{val} -> {sub} ({target_zone})"
                        sub_counts[sub] = sub_counts.get(sub, 0) + 1
                    else:
                        entry[p_col] = f"{val} -> NO STAFF"
                else:
                    entry[p_col] = None
            results.append(entry)

    return pd.DataFrame(results)

# ---------- 5. UI ----------
days = timetable['day'].dropna().unique().tolist()
sel_day = st.selectbox("Select Day:", options=days)
day_df = timetable[timetable['day'] == sel_day].copy()

st.subheader(f"🏛️ Master Timetable: {sel_day}")
st.dataframe(day_df[['tname'] + period_cols], height=250)

st.divider()
# UI Filter to keep the list clean
selectable_teachers = sorted([t for t in day_df['tname'].unique() if not any(ex.lower() in str(t).lower() for ex in [n.lower() for n in PERMANENT_EXEMPT])])
abs_list = st.multiselect("🚩 Select Absent Teachers:", options=selectable_teachers)

if abs_list:
    st.subheader("📋 Absentee View")
    st.dataframe(day_df[day_df['tname'].isin(abs_list)][['tname'] + period_cols])
    
    if st.button("🚀 Generate Substitution Plan"):
        st.subheader("📝 Final Plan")
        res = arrange_substitutions(day_df, abs_list)
        st.dataframe(res, use_container_width=True)
        st.download_button("📥 Download Excel", data=to_excel(res), file_name=f"Subs_{sel_day}.xlsx")
