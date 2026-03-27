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
st.title("Teacher Substitution Scheduler — Destination Priority")

# ---------- 1. CONFIG ----------
LOCAL_FILENAME = "TT_apr26.xlsx"   
PERMANENT_EXEMPT = ["PRINCIPAL", "ARCHANA SRIVASTAVA"] 

# ---------- 2. UTILITIES ----------
def get_zone(section_label):
    match = re.search(r'(\d+)', str(section_label))
    if not match: return "Main"
    grade = int(match.group())
    return "Junior" if 6 <= grade <= 7 else "Main"

def cell_has_class(val):
    if pd.isna(val): return False
    s = str(val).strip().lower()
    return s not in ["", "free", "vacant", "zero pd", "0 pd", "zero", "off"]

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
day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
timetable['day'] = pd.Categorical(timetable['day'].str.strip().str.capitalize(), categories=day_order, ordered=True)
period_cols = sorted([c for c in timetable.columns if re.fullmatch(r'p\d+', c)], key=lambda x: int(re.findall(r'\d+', x)[0]))

# ---------- 4. THE ENGINE ----------
def arrange_substitutions(day_df, absent_teachers):
    exempt_clean = [n.strip().upper() for n in PERMANENT_EXEMPT]
    abs_clean = [n.strip().upper() for n in absent_teachers]
    
    available_staff = [t for t in day_df['tname'].dropna().unique() 
                       if t.strip().upper() not in abs_clean and t.strip().upper() not in exempt_clean]
    
    sub_counts = {t: 0 for t in available_staff}
    teacher_load = {t: [False] * len(period_cols) for t in available_staff}
    teacher_schedule = {t: [None] * len(period_cols) for t in available_staff}

    for t in available_staff:
        row = day_df[day_df['tname'] == t].iloc[0]
        for idx, p in enumerate(period_cols):
            val = row.get(p)
            if cell_has_class(val):
                teacher_load[t][idx] = True
                teacher_schedule[t][idx] = get_zone(val)

    results = {t: {p: None for p in period_cols} for t in absent_teachers}

    for idx, p_col in enumerate(period_cols):
        current_absents = list(absent_teachers)
        random.shuffle(current_absents)
        for abs_t in current_absents:
            val = day_df[day_df['tname'] == abs_t].iloc[0].get(p_col)
            if cell_has_class(val):
                sec_label = str(val).strip()
                target_zone = get_zone(sec_label)
                
                candidates = [t for t in available_staff if not teacher_load[t][idx]]
                
                def get_priority_score(t):
                    # Start with total workload (lower is better)
                    score = sub_counts[t] * 20
                    
                    # --- FORWARD LOOKING PRIORITY ---
                    next_idx = idx + 1
                    next_loc = None
                    if next_idx < len(period_cols):
                        # Find their next actual class
                        for ahead in range(next_idx, len(period_cols)):
                            if teacher_load[t][ahead]:
                                next_loc = teacher_schedule[t][ahead]
                                break
                    
                    # RULE: If their next class is where the sub is -> BIG PRIORITY
                    if next_loc == target_zone:
                        score -= 80  # They need to go there anyway. Move them now!
                    
                    # RULE: If they are currently in the target zone (from prev period)
                    prev_idx = idx - 1
                    if prev_idx >= 0 and teacher_schedule[t][prev_idx] == target_zone:
                        score -= 40  # Already there, save the walk.

                    # RULE: If they have to switch buildings for their next class
                    if next_loc and next_loc != target_zone:
                        score += 100 # Keep them free so they can walk to their next building.
                    
                    return score

                candidates.sort(key=get_priority_score)

                if candidates:
                    sub = candidates[0]
                    results[abs_t][p_col] = f"{sec_label} -> {sub} ({target_zone})"
                    teacher_load[sub][idx] = True
                    sub_counts[sub] += 1
                    teacher_schedule[sub][idx] = target_zone 
                else: 
                    results[abs_t][p_col] = f"{sec_label} -> NO STAFF"

    final_output = []
    for t, p_data in results.items():
        row = {"Absent Teacher": t}; row.update(p_data); final_output.append(row)
    return pd.DataFrame(final_output)

# ---------- 5. UI ----------
mode = st.radio("View:", ["Daily", "Weekly"], horizontal=True)

if mode == "Daily":
    days = timetable['day'].dropna().unique().tolist()
    sel_day = st.selectbox("Select Day:", options=days)
    day_df = timetable[timetable['day'] == sel_day].copy()
    abs_list = st.multiselect("Absent Teachers:", options=day_df['tname'].dropna().unique().tolist())
    if st.button("Generate Substitutions"):
        res = arrange_substitutions(day_df, abs_list)
        st.dataframe(res)
        st.download_button("📥 Download Excel", data=to_excel(res), file_name=f"Subs_{sel_day}.xlsx")
else:
    abs_week = st.multiselect("Absent Teachers (Weekly):", options=timetable['tname'].dropna().unique().tolist())
    if st.button("Generate Weekly Table"):
        all_res = []
        for d in day_order:
            d_df = timetable[timetable['day'] == d]
            if not d_df.empty and abs_week:
                r = arrange_substitutions(d_df, abs_week); r.insert(0, "Day", d); all_res.append(r)
        if all_res:
            final = pd.concat(all_res)
            st.dataframe(final)
            st.download_button("📥 Download Weekly Excel", data=to_excel(final), file_name="Weekly_Subs.xlsx")
