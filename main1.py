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
st.title("Teacher Substitution Scheduler — Global Name Cleanup")

# ---------- 1. CONFIG ----------
LOCAL_FILENAME = "TT_apr26.xlsx"   
# Use Cleaned Uppercase Names here
PERMANENT_EXEMPT = ["PRINCIPAL", "VICE PRINCIPAL", "V.P.", "ARCHANA SRIVASTAVA"] 

# ---------- 2. UTILITIES ----------
def clean_string(val):
    """Global cleaner for any cell: removes Mr. Ms. Mrs. Miss and extra spaces."""
    if pd.isna(val) or not isinstance(val, (str, object)): 
        return val
    s = str(val).strip()
    # Removes salutations at the start of any string (case insensitive)
    s = re.sub(r'^(Mr|Ms|Mrs|Miss)\.?\s+', '', s, flags=re.IGNORECASE)
    return s.strip()

def get_zone(section_label):
    match = re.search(r'(\d+)', str(section_label))
    if not match: return "Main"
    grade = int(match.group())
    return "Junior" if 6 <= grade <= 7 else "Main"

def is_exempt(name):
    if not name: return False
    return clean_string(name).upper() in [n.upper() for n in PERMANENT_EXEMPT]

def cell_has_class(val):
    if pd.isna(val): return False
    s = str(val).strip().lower()
    if s in ["", "free", "vacant", "zero pd", "0 pd", "zero", "off", "skill"]:
        return False
    return True

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Substitutions')
    return output.getvalue()

# ---------- 3. LOAD & CLEAN DATA ----------
def load_and_clean():
    df = None
    if os.path.exists(LOCAL_FILENAME):
        try: 
            df = pd.read_excel(LOCAL_FILENAME, header=0)
        except: 
            pass
            
    if df is None:
        uploaded = st.file_uploader("Upload Timetable Excel", type=["xlsx"])
        if not uploaded: st.stop()
        df = pd.read_excel(uploaded, header=0)

    # Clean the column headers
    df.columns = df.columns.str.strip().str.lower()
    
    # FIX: Use .map() instead of .applymap() for newer Pandas versions
    # This cleans every cell in the dataframe globally
    try:
        df = df.map(clean_string)
    except AttributeError:
        # Fallback for older pandas versions
        df = df.applymap(clean_string)
    
    return df

timetable = load_and_clean()

day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
timetable['day'] = pd.Categorical(timetable['day'].str.strip().str.capitalize(), categories=day_order, ordered=True)
period_cols = sorted([c for c in timetable.columns if re.fullmatch(r'p\d+', c)], key=lambda x: int(re.findall(r'\d+', x)[0]))

# ---------- 4. THE ENGINE ----------
def arrange_substitutions(day_df, absent_teachers):
    abs_clean = [clean_string(a).upper() for a in absent_teachers]
    
    available_staff = [t for t in day_df['tname'].dropna().unique() 
                       if not is_exempt(t) and t.upper() not in abs_clean]
    
    sub_counts = {t: 0 for t in available_staff}
    teacher_load = {t: [False] * len(period_cols) for t in available_staff}
    teacher_schedule = {t: [None] * len(period_cols) for t in available_staff}

    for t in available_staff:
        rows = day_df[day_df['tname'] == t]
        if rows.empty: continue
        row = rows.iloc[0]
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
            if is_exempt(abs_t): continue
            
            rows = day_df[day_df['tname'] == abs_t]
            if rows.empty: continue
            val = rows.iloc[0].get(p_col)
            
            if cell_has_class(val):
                sec_label = str(val).strip()
                target_zone = get_zone(sec_label)
                candidates = [t for t in available_staff if not teacher_load[t][idx]]
                
                def get_priority_score(t):
                    score = sub_counts[t] * 20
                    next_idx = idx + 1
                    next_loc = None
                    if next_idx < len(period_cols):
                        for ahead in range(next_idx, len(period_cols)):
                            if teacher_load[t][ahead]:
                                next_loc = teacher_schedule[t][ahead]
                                break
                    if next_loc == target_zone: score -= 80  
                    prev_idx = idx - 1
                    if prev_idx >= 0 and teacher_schedule[t][prev_idx] == target_zone: score -= 40  
                    if next_loc and next_loc != target_zone: score += 100 
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
        if not is_exempt(t):
            row = {"Absent Teacher": t}; row.update(p_data); final_output.append(row)
    return pd.DataFrame(final_output)

# ---------- 5. UI ----------
mode = st.radio("View Mode:", ["Daily", "Weekly"], horizontal=True)

if mode == "Daily":
    days = timetable['day'].dropna().unique().tolist()
    sel_day = st.selectbox("Select Day:", options=days)
    day_df = timetable[timetable['day'] == sel_day].copy()
    
    st.subheader(f"🏛️ Full School Timetable: {sel_day} (Cleaned)")
    st.dataframe(day_df[['tname'] + period_cols], height=300)
    
    st.divider()
    all_teachers = sorted(day_df['tname'].dropna().unique().tolist())
    selectable_teachers = [t for t in all_teachers if not is_exempt(t)]
    
    abs_list = st.multiselect("🚩 Select Absent Teachers:", options=selectable_teachers)
    
    if abs_list:
        st.subheader("📋 Targeted Absentee Schedule")
        absentee_schedule = day_df[day_df['tname'].isin(abs_list)]
        st.dataframe(absentee_schedule[['tname'] + period_cols])
        
        if st.button("🚀 Generate Substitution Plan"):
            st.subheader("📝 Proposed Substitution Table")
            res = arrange_substitutions(day_df, abs_list)
            st.dataframe(res, use_container_width=True)
            st.download_button("📥 Download Excel", data=to_excel(res), file_name=f"Subs_{sel_day}.xlsx")

else:
    st.subheader("📅 Weekly Timetable Overview (Cleaned)")
    st.dataframe(timetable[['day', 'tname'] + period_cols], height=400)
    
    teachers_all = sorted([t for t in timetable['tname'].dropna().unique().tolist() if not is_exempt(t)])
    abs_week = st.multiselect("Select Absent Teachers (Weekly):", options=teachers_all)
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
