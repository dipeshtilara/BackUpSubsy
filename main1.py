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
LOCAL_FILENAME = "TT_apr26.xlsx"   # your uploaded file name
DEFAULT_PERIOD_COUNT = 9  # p0..p8

# --- MASTER DATA FOR SMART SUBSTITUTION ---
TEACHER_SUBJECTS = {
    # Main Building (8-12) & Specialists
    "BHAVESH": "PHY", "LAVKUSH": "PHY", "DEEPTI": "CHEM", "KAVITA": "CHEM",
    "ANUJ D.": "MATH", "S C MISHRA": "MATH", "PGT BIO": "BIO", "YOGENDRA": "BIO",
    "PRIYANKA": "ENG", "SUBODH": "ENG", "VIRBAHADUR": "ENG", "M.JOSHI": "ENG", "STUTI": "ENG",
    "PURAN": "HPE", "PANKAJ": "HPE", "MADAN": "HPE", "P.K.DUBEY": "A/C",
    "ANSHULI": "BST", "VIRBHADRA": "ECO", "MANASI": "ECO", "RAHUL V.": "A/C",
    "KALPLATA": "GEOG", "RAHUL R.": "HIST", "PRIYA P.": "POL.SCI", "RISHIBHA": "PSY",
    "TUSHAR": "PHY", 
    
    # Computer/AI/IP/CS Department
    "DIPESH": "IP", "AMIT T.": "AI/CS", "ANUJ T.": "AI", "APEKSHA": "AI", "ROHIT": "AI",

    # Junior Building (6-7) & Middle School
    "ARCHANA S.": "SST", "ABHILASHA": "ENG", "RINI ROY": "ENG", "TULIKA": "ENG", 
    "RUBY": "HINDI/SANS", "SWARNLATA": "HINDI/SANS", "DURGA DUTT": "SANSKRIT",
    "BABITA": "MATH", "SHUBHAM": "CT", "SHUBHA M": "MATH", "JYOTI": "MATH", "SIMPY": "MATH",
    "VINITA": "SCI", "POOJA": "SCI", "KOMAL": "SCI", "SHWETA": "SCI", "KRITI": "SCI",
    "HIMA": "SST", "KASHISH": "SST", "GUNJAN K.": "SST", "PRIYA SRI.": "SST",
    "NAMRATA A": "HPE", "SAPNA": "ART", "NAWAZ": "ART", "SACHIN": "MUSIC", "AMITABH": "MUSIC"
}

# ---------- UTILITIES ----------
def get_zone(section_label):
    """Junior Building (6-7) vs Main Building (8-12)"""
    match = re.search(r'(\d+)', str(section_label))
    if not match: return "Main"
    grade = int(match.group())
    return "Junior" if 6 <= grade <= 7 else "Main"

def is_compatible(sec_a, sec_b, subject):
    """Stream logic for Senior secondary merges."""
    m_a = re.search(r'(\d+)([A-H])', str(sec_a).upper())
    m_b = re.search(r'(\d+)([A-H])', str(sec_b).upper())
    if not m_a or not m_b: return False
    g1, s1 = m_a.groups(); g2, s2 = m_b.groups()
    if g1 != g2: return False 
    if subject in ["ENG", "HPE", "HINDI"]: return True 
    sci = {'A', 'B', 'C', 'D'}
    if s1 in sci and s2 in sci:
        if subject in ["PHY", "CHEM"]: return True
        if s1 in ['A','B'] and s2 in ['A','B'] and subject == "MATH": return True
        if s1 in ['C','D'] and s2 in ['C','D'] and subject == "BIO": return True
    return False

# ---------- LOAD FILE ----------
def load_timetable():
    if os.path.exists(LOCAL_FILENAME):
        try:
            df = pd.read_excel(LOCAL_FILENAME, header=0)
            st.success(f"Loaded local file: {LOCAL_FILENAME}")
            return df
        except Exception as e:
            st.error(f"Could not read local file {LOCAL_FILENAME}: {e}")
    uploaded = st.file_uploader("Upload timetable Excel (xlsx).", type=["xlsx"])
    if not uploaded:
        st.info("Place TT_apr26.xlsx next to this script or upload an Excel file.")
        st.stop()
    df = pd.read_excel(uploaded, header=0)
    return df

timetable = load_timetable()
timetable.columns = timetable.columns.str.strip().str.lower()
day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
timetable['day'] = timetable['day'].str.strip().str.capitalize()
timetable['day'] = pd.Categorical(timetable['day'], categories=day_order, ordered=True)

# Detect period columns
cols = list(timetable.columns)
period_cols = [c for c in cols if re.fullmatch(r'p\d+', c)]
if not period_cols:
    period_cols = [c for c in cols if re.match(r'p[_\-\s]?\d+', c)]
if not period_cols:
    period_cols = [f"p{i}" for i in range(DEFAULT_PERIOD_COUNT)]
expected_periods = sorted(period_cols, key=lambda x: int(re.findall(r'\d+', x)[0]))

# ---------- UI: view mode & off-classes ----------
view_mode = st.radio("Select view mode:", ["Daily", "Weekly"], horizontal=True)
off_classes = st.checkbox("Mark specific classes as off?")
off_classes_list = []
if off_classes:
    sample_vals = []
    for p in expected_periods:
        sample_vals.extend(timetable[p].dropna().astype(str).tolist())
    classes_list = sorted({s.strip() for s in sample_vals if s and s.strip()})
    off_classes_list = st.multiselect("Select off class substrings:", options=classes_list)

def cell_has_class(val, period_name=None):
    if pd.isna(val): return False
    s = str(val).strip()
    if s == "": return False
    s_lower = s.lower()
    if off_classes_list:
        for off in off_classes_list:
            if off and off.lower() in s_lower: return False
    if period_name and period_name.lower() == "p0":
        return "skill" in s_lower
    if (("zero pd" in s_lower) or (s_lower == "0 pd") or (s_lower == "zero")) and ("skill" not in s_lower):
        return False
    return True

# ---------- CORE SUBSTITUTION ENGINE ----------
def arrange_substitutions(day_df, absent_teachers):
    expected = expected_periods
    available_staff = [t for t in day_df['tname'].dropna().unique() if t not in absent_teachers]
    
    sub_counts = {t: 0 for t in available_staff}
    teacher_load = {t: [False] * len(expected) for t in available_staff}
    teacher_locations = {t: [None] * len(expected) for t in available_staff}
    
    for t in available_staff:
        row = day_df[day_df['tname'] == t].iloc[0]
        for idx, p in enumerate(expected):
            val = row.get(p)
            if cell_has_class(val, p):
                teacher_load[t][idx] = True
                teacher_locations[t][idx] = get_zone(val)

    results = {t: {p: None for p in expected} for t in absent_teachers}

    for idx, p_col in enumerate(expected):
        current_absents = list(absent_teachers)
        random.shuffle(current_absents)
        
        for abs_t in current_absents:
            abs_row = day_df[day_df['tname'] == abs_t].iloc[0]
            val = abs_row.get(p_col)
            
            if cell_has_class(val, p_col):
                sec_label = str(val).strip()
                target_zone = get_zone(sec_label)
                abs_subj = TEACHER_SUBJECTS.get(abs_t.upper(), "GEN")
                g_match = re.search(r'(\d+)', sec_label)
                grade = int(g_match.group()) if g_match else 10

                candidates = [t for t in available_staff if not teacher_load[t][idx]]
                safe_cands = []
                next_idx = idx + 1
                for t in candidates:
                    if next_idx < len(expected):
                        next_loc = teacher_locations[t][next_idx]
                        if next_loc and next_loc != target_zone: continue 
                    
                    temp = list(teacher_load[t]); temp[idx] = True
                    streak, max_s = 0, 0
                    for b in temp:
                        if b: streak += 1; max_s = max(max_s, streak)
                        else: streak = 0
                    half = range(0,5) if idx < 5 else range(5, len(expected))
                    if max_s <= 4 and sum(temp[i] for i in half) <= 4:
                        safe_cands.append(t)
                
                final_pool = safe_cands if safe_cands else candidates
                comp_dept = {"DIPESH", "AMIT T.", "ANUJ T.", "APEKSHA"}
                is_comp_period = abs_subj in ["AI", "IP", "CS", "AI/CS"]

                def get_priority_score(t):
                    score = sub_counts[t] * 10
                    t_up = t.upper()
                    if is_comp_period and t_up in comp_dept: return score - 40
                    if t_up == "TUSHAR":
                        if abs_subj == "PHY": return score - 35
                        if abs_subj == "MATH" and 6 <= grade <= 8: return score - 30
                    if TEACHER_SUBJECTS.get(t_up) == abs_subj: return score - 20
                    return score

                final_pool.sort(key=get_priority_score)

                if final_pool:
                    sub = final_pool[0]
                    results[abs_t][p_col] = f"{sec_label} -> {sub} ({target_zone})"
                    teacher_load[sub][idx] = True
                    sub_counts[sub] += 1
                    teacher_locations[sub][idx] = target_zone
                else:
                    working = day_df[(~day_df['tname'].isin(absent_teachers)) & (day_df[p_col].apply(lambda x: cell_has_class(x, p_col)))]
                    merge_t = next((r['tname'] for _, r in working.iterrows() if get_zone(r[p_col]) == target_zone and is_compatible(sec_label, r[p_col], abs_subj)), None)
                    results[abs_t][p_col] = f"{sec_label} -> MERGE ({merge_t})" if merge_t else f"{sec_label} -> NO SUB"

    final_output = []
    for t, p_data in results.items():
        row_dict = {"tname": t}
        row_dict.update(p_data)
        final_output.append(row_dict)
    return pd.DataFrame(final_output)

# ---------- DAILY VIEW ----------
if view_mode == "Daily":
    days = timetable['day'].dropna().unique().tolist()
    selected_day = st.selectbox("Select day:", options=days)
    day_df = timetable[timetable['day'] == selected_day].copy()
    st.write(f"### Timetable for {selected_day}")
    st.dataframe(day_df)

    absent_teachers = st.multiselect("Select absent teachers (Daily):", options=day_df['tname'].dropna().unique().tolist())

    if absent_teachers:
        st.write("### Classes handled by selected absent teachers")
        st.dataframe(day_df[day_df['tname'].isin(absent_teachers)])

    if st.checkbox("Compute substitutions for this day"):
        subs = arrange_substitutions(day_df, absent_teachers)
        if not subs.empty:
            st.write("### Substitution Schedule (Daily)")
            st.dataframe(subs)
        else:
            st.info("No substitutions found.")

# ---------- WEEKLY VIEW ----------
else:
    st.write("### Weekly view")
    teachers_all = timetable['tname'].dropna().unique().tolist()
    teacher_choice = st.selectbox("Select teacher (or All):", options=["All"] + teachers_all)

    if teacher_choice == "All":
        totals = []
        for t in teachers_all:
            rows = timetable[timetable['tname'] == t]
            total = sum(cell_has_class(r.get(p), p) for _, r in rows.iterrows() for p in expected_periods)
            totals.append({"tname": t, "total_periods_week": total, "num_days_present": rows['day'].nunique()})
        st.dataframe(pd.DataFrame(totals).sort_values(by='total_periods_week', ascending=False))
    else:
        trows = timetable[timetable['tname'] == teacher_choice].sort_values(by='day')
        st.dataframe(trows)

    absent_week = []
    if st.checkbox("Select absent teachers (Weekly)?"):
        absent_week = st.multiselect("Select absent teachers (Weekly):", options=teachers_all)

    if st.checkbox("Compute substitutions for the whole week"):
        subs_all = []
        for d in day_order:
            d_df = timetable[timetable['day'] == d]
            if not d_df.empty:
                s_day = arrange_substitutions(d_df, absent_week)
                if not s_day.empty:
                    s_day.insert(0, "day", d)
                    subs_all.append(s_day)
        if subs_all:
            st.write("### Weekly Substitution Schedule")
            st.dataframe(pd.concat(subs_all, ignore_index=True))

st.write("---")
st.caption("v2.0: Building-aware, AI-Priority, Streak-Protection enabled.")
