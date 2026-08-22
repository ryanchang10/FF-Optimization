import streamlit as st
import pandas as pd
import difflib
import re

# --- Helper function to normalize names ---
def normalize_name(name):
    return re.sub(r'[^a-z]', '', name.lower())  # remove non-letters, lowercase


# --- Load Data ---
@st.cache_data
def load_data():
    qb = pd.read_csv("qb_predictions26.csv")
    rb = pd.read_csv("rb_predictions26.csv")
    wr = pd.read_csv("wr_predictions26.csv")
    te = pd.read_csv("te_predictions26.csv")

    qb["Position"] = "QB"
    rb["Position"] = "RB"
    wr["Position"] = "WR"
    te["Position"] = "TE"

    df = pd.concat([qb, rb, wr, te], ignore_index=True)

    # If predicted_diff isn't in the source CSVs, default to 0 so the app
    # doesn't crash. If your CSVs use a different column name for this,
    # rename it here.
    if "predicted_diff" not in df.columns:
        df["predicted_diff"] = 0.0

    # Add normalized player name for lookup
    df["player_normalized"] = df["player"].apply(normalize_name)

    return df


# --- Recalculate PAR (drop-off to next best player) for a given player pool ---
def recalculate_par(df):
    updated = []

    for position in ["QB", "RB", "WR", "TE"]:
        pos_df = df[df["Position"] == position].copy()
        pos_df = pos_df.sort_values(by="avg_fantpt", ascending=False).reset_index(drop=True)
        pos_df["par"] = pos_df["avg_fantpt"] - pos_df["avg_fantpt"].shift(-1)
        updated.append(pos_df)

    return pd.concat(updated, ignore_index=True)


# --- Min-max normalize a series to 0-1 so different metrics can be combined fairly ---
def normalize_series(s):
    s = s.fillna(0)
    if s.max() == s.min():
        return pd.Series([0.5] * len(s), index=s.index)
    return (s - s.min()) / (s.max() - s.min())


# --- Build empty roster slot list from league config ---
def build_roster_slots(config):
    slots = []

    def add_slots(slot_type, count):
        for i in range(count):
            label = f"{slot_type}{i + 1}" if count > 1 else slot_type
            slots.append({
                "slot_type": slot_type,
                "label": label,
                "player": None,
                "position": None,
                "avg_fantpt": None,
                "par": None,
                "predicted_diff": None,
            })

    add_slots("QB", config["QB"])
    add_slots("RB", config["RB"])
    add_slots("WR", config["WR"])
    add_slots("TE", config["TE"])
    add_slots("FLEX", config["FLEX"])
    add_slots("BENCH", config["BENCH"])

    return slots


# --- Determine which team is on the clock for a given overall pick number ---
def team_on_the_clock(pick_number, num_teams):
    round_num = (pick_number - 1) // num_teams + 1
    pos_in_round = (pick_number - 1) % num_teams + 1
    if round_num % 2 == 1:
        return pos_in_round
    else:
        return num_teams - pos_in_round + 1


# --- Fill the first open roster slot matching a drafted player's position ---
def fill_roster_slot(roster, position, player_name, avg_fantpt, par, predicted_diff):
    def try_fill(slot_type):
        for slot in roster:
            if slot["slot_type"] == slot_type and slot["player"] is None:
                slot["player"] = player_name
                slot["position"] = position
                slot["avg_fantpt"] = avg_fantpt
                slot["par"] = par
                slot["predicted_diff"] = predicted_diff
                return True
        return False

    if position == "QB":
        return try_fill("QB") or try_fill("BENCH")

    if position in ("RB", "WR", "TE"):
        return try_fill(position) or try_fill("FLEX") or try_fill("BENCH")

    # Anything else (D/ST, K, etc.) just goes to BENCH if there's room
    return try_fill("BENCH")


# --- Rebuild all derived state (roster, drafted set, pick count) from the draft log ---
def rebuild_state():
    config = st.session_state.league_config
    log = st.session_state.draft_log

    st.session_state.drafted_normalized = {e["normalized"] for e in log}
    st.session_state.pick_count = len(log)

    roster = build_roster_slots(config)
    for idx, entry in enumerate(log):
        pick_number = idx + 1
        if team_on_the_clock(pick_number, config["num_teams"]) == config["draft_slot"]:
            fill_roster_slot(
                roster,
                entry["position"],
                entry["player"],
                entry["avg_fantpt"],
                entry.get("par"),
                entry.get("predicted_diff"),
            )

    st.session_state.my_roster = roster


# --- Figure out which positions your team still needs (starters + flex) ---
def compute_position_needs(roster):
    direct_open = {
        pos: sum(1 for s in roster if s["slot_type"] == pos and s["player"] is None)
        for pos in ["QB", "RB", "WR", "TE"]
    }
    flex_open = sum(1 for s in roster if s["slot_type"] == "FLEX" and s["player"] is None)

    needed = set()
    for pos, open_count in direct_open.items():
        if open_count > 0:
            needed.add(pos)
    if flex_open > 0:
        needed.update(["RB", "WR", "TE"])

    return needed


# --- Load the full dataset, with a static PAR computed once against the full field ---
# This "master" PAR/predicted_diff is what gets stored with each pick and shown on
# your roster - it reflects a player's value at the time you drafted them relative
# to the whole player pool, and won't shift around as other players get drafted.
players_df = load_data()
players_df = recalculate_par(players_df)

st.set_page_config(layout="wide")
st.title("🏈 Fantasy Football Draft Tool")

# --- One-time league setup ---
if "league_config" not in st.session_state:
    st.subheader("⚙️ League Setup")
    st.write("Set this up once before the draft starts so I can track your roster automatically.")

    with st.form("setup_form"):
        num_teams = st.number_input("Number of teams in your league", min_value=2, max_value=20, value=12)
        draft_slot = st.number_input("Your draft position (pick order)", min_value=1, max_value=20, value=1)

        st.markdown("**Starting roster slots**")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        qb_slots = col1.number_input("QB", min_value=0, max_value=5, value=1)
        rb_slots = col2.number_input("RB", min_value=0, max_value=5, value=2)
        wr_slots = col3.number_input("WR", min_value=0, max_value=5, value=2)
        te_slots = col4.number_input("TE", min_value=0, max_value=5, value=1)
        flex_slots = col5.number_input("FLEX", min_value=0, max_value=5, value=1)
        bench_slots = col6.number_input("BENCH", min_value=0, max_value=15, value=6)

        setup_submitted = st.form_submit_button("Start Draft")

    if setup_submitted:
        if draft_slot > num_teams:
            st.error("Your draft position can't be greater than the number of teams.")
        else:
            st.session_state.league_config = {
                "num_teams": num_teams,
                "draft_slot": draft_slot,
                "QB": qb_slots,
                "RB": rb_slots,
                "WR": wr_slots,
                "TE": te_slots,
                "FLEX": flex_slots,
                "BENCH": bench_slots,
            }
            st.session_state.draft_log = []
            rebuild_state()
            st.rerun()

    st.stop()

config = st.session_state.league_config

# --- Sidebar: league info, recommendation weights, and reset ---
with st.sidebar:
    st.markdown("### League Setup")
    st.write(f"Teams: **{config['num_teams']}**")
    st.write(f"Your draft slot: **{config['draft_slot']}**")
    st.write(f"Picks logged so far: **{st.session_state.pick_count}**")

    st.markdown("### 🎛️ Recommendation Weights")
    st.caption("How much each factor matters when ranking who to draft next.")
    w_par = st.slider("Positional drop-off (PAR)", 0, 100, 40)
    w_pts = st.slider("Projected points (avg_fantpt)", 0, 100, 40)
    w_diff = st.slider("Projected diff", 0, 100, 20)

    if st.button("🔄 Reset Draft"):
        for key in ["league_config", "my_roster", "drafted_normalized", "pick_count", "draft_log"]:
            st.session_state.pop(key, None)
        st.rerun()

# Normalize weights so they sum to 1 (avoid divide-by-zero if user sets all to 0)
_weight_sum = w_par + w_pts + w_diff
if _weight_sum == 0:
    w_par_n, w_pts_n, w_diff_n = 0.4, 0.4, 0.2
else:
    w_par_n, w_pts_n, w_diff_n = w_par / _weight_sum, w_pts / _weight_sum, w_diff / _weight_sum

# --- Whose turn is it? ---
next_pick_number = st.session_state.pick_count + 1
on_the_clock = team_on_the_clock(next_pick_number, config["num_teams"])
is_my_turn = on_the_clock == config["draft_slot"]

if is_my_turn:
    st.info(f"📢 Pick #{next_pick_number} — **You're on the clock!**")
else:
    st.write(f"Pick #{next_pick_number} — Team {on_the_clock} on the clock")


# --- Shared pick-adding logic used by every entry method below ---
def add_pick(player_name_raw, silent=False):
    normalized_input = normalize_name(player_name_raw)

    if normalized_input in st.session_state.drafted_normalized:
        if not silent:
            st.warning(f"{player_name_raw} has already been marked as drafted.")
        return False

    if normalized_input in players_df["player_normalized"].values:
        match = players_df[players_df["player_normalized"] == normalized_input].iloc[0]
        entry = {
            "player": match["player"],
            "position": match["Position"],
            "avg_fantpt": match["avg_fantpt"],
            "predicted_diff": match["predicted_diff"],
            "par": match["par"],
            "normalized": normalized_input,
        }
        st.session_state.draft_log.append(entry)
        rebuild_state()
        pick_num = len(st.session_state.draft_log)
        landed_on_team = " — added to your roster!" if team_on_the_clock(pick_num, config["num_teams"]) == config["draft_slot"] else ""
        if not silent:
            st.success(f"Pick #{pick_num}: {match['player']} ({match['Position']}){landed_on_team}")
        return True
    else:
        if not silent:
            st.warning(f"No exact match found for '{player_name_raw}'.")
            close = difflib.get_close_matches(
                normalized_input, players_df["player_normalized"].tolist(), n=5, cutoff=0.6
            )
            if close:
                suggestions = players_df[players_df["player_normalized"].isin(close)]["player"].tolist()
                st.info("Did you mean: " + ", ".join(suggestions) + "?")
        return False


# --- Draft entry: three ways to log a pick to cut down on missed/mistyped picks ---
st.subheader("📝 Log a Pick")

drafted_set_now = st.session_state.drafted_normalized
available_now = players_df[~players_df["player_normalized"].isin(drafted_set_now)]

tab1, tab2, tab3 = st.tabs(["🔍 Search & Select", "⌨️ Type Name", "📋 Full List"])

with tab1:
    st.caption("Pick from the list of undrafted players — this avoids typos entirely.")
    sorted_avail = available_now.sort_values(by="avg_fantpt", ascending=False)
    option_labels = [f"{row.player} ({row.Position})" for row in sorted_avail.itertuples()]
    label_to_name = dict(zip(option_labels, sorted_avail["player"]))

    if option_labels:
        selected_label = st.selectbox(
            "Select drafted player",
            option_labels,
            index=None,
            placeholder="Type to search...",
            key="select_player_input",
        )
        if st.button("Add Selected Pick"):
            if selected_label:
                add_pick(label_to_name[selected_label])
                st.rerun()
            else:
                st.warning("Please select a player first.")
    else:
        st.write("No players remaining.")

with tab2:
    with st.form("draft_form", clear_on_submit=True):
        player_drafted = st.text_input("Enter drafted player name:", key="player_input")
        submitted = st.form_submit_button("Add Pick")
    if submitted and player_drafted:
        add_pick(player_drafted)

with tab3:
    st.caption("Check off players as they're drafted — handy for logging several other teams' picks at once.")
    fcol1, fcol2 = st.columns([1, 2])
    with fcol1:
        pos_filter = st.selectbox("Position", ["All", "QB", "RB", "WR", "TE"], key="full_list_pos_filter")
    with fcol2:
        search_filter = st.text_input("Search player name", key="full_list_search")

    list_df = available_now.copy()
    if pos_filter != "All":
        list_df = list_df[list_df["Position"] == pos_filter]
    if search_filter:
        list_df = list_df[list_df["player"].str.contains(search_filter, case=False, na=False)]

    list_df = list_df.sort_values(by="avg_fantpt", ascending=False)
    list_df = list_df[["player", "Position", "avg_fantpt", "par", "predicted_diff"]].copy()
    list_df.insert(0, "Drafted", False)

    edited_df = st.data_editor(
        list_df,
        use_container_width=True,
        hide_index=True,
        disabled=["player", "Position", "avg_fantpt", "par", "predicted_diff"],
        key="full_list_editor",
    )

    if st.button("Add Checked Players to Draft"):
        checked = edited_df[edited_df["Drafted"] == True]
        if checked.empty:
            st.warning("No players checked.")
        else:
            added = 0
            for _, row in checked.iterrows():
                if add_pick(row["player"], silent=True):
                    added += 1
            st.success(f"Added {added} pick(s).")
            st.rerun()

# --- Log a D/ST or K pick (not in the ranked player pool, but still consumes a pick) ---
st.subheader("🛡️ Log a D/ST or K Pick")
st.caption(
    "D/ST and Kickers aren't in the ranked player data, so use this to keep pick tracking "
    "and roster assignment accurate when one gets drafted."
)
with st.form("dst_k_form", clear_on_submit=True):
    dk_col1, dk_col2 = st.columns([3, 1])
    dst_k_name = dk_col1.text_input("Team/Player name (optional)", placeholder="e.g. 49ers D/ST or Justin Tucker")
    dst_k_type = dk_col2.radio("Type", ["D/ST", "K"], horizontal=True)
    dst_k_submit = st.form_submit_button("Log Pick")

if dst_k_submit:
    label = dst_k_name.strip() if dst_k_name.strip() else f"Unnamed {dst_k_type}"
    normalized = "dstk_" + normalize_name(label) + "_" + dst_k_type.lower().replace("/", "")
    entry = {
        "player": label,
        "position": dst_k_type,
        "avg_fantpt": 0.0,
        "predicted_diff": 0.0,
        "par": None,
        "normalized": normalized,
    }
    st.session_state.draft_log.append(entry)
    rebuild_state()
    pick_num = len(st.session_state.draft_log)
    landed_on_team = " — added to your roster!" if team_on_the_clock(pick_num, config["num_teams"]) == config["draft_slot"] else ""
    st.success(f"Pick #{pick_num}: {label} ({dst_k_type}){landed_on_team}")
    st.rerun()

# --- Undo / remove picks ---
st.subheader("↩️ Undo / Remove a Pick")
log = st.session_state.draft_log

col_a, col_b = st.columns([1, 2])
with col_a:
    if st.button("Undo Last Pick", disabled=len(log) == 0):
        log.pop()
        rebuild_state()
        st.rerun()

with col_b:
    if log:
        options = [f"Pick #{i + 1}: {e['player']} ({e['position']})" for i, e in enumerate(log)]
        selected = st.selectbox("Or remove a specific pick:", options, label_visibility="collapsed")
        if st.button("Remove Selected Pick"):
            idx = options.index(selected)
            log.pop(idx)
            rebuild_state()
            st.rerun()

if log:
    with st.expander("📜 Full Draft Log"):
        log_df = pd.DataFrame([
            {
                "Pick #": i + 1,
                "Player": e["player"],
                "Position": e["position"],
                "Avg FantPt": e["avg_fantpt"],
                "Projected Diff": e.get("predicted_diff"),
            }
            for i, e in enumerate(log)
        ])
        st.dataframe(log_df, use_container_width=True, hide_index=True)

# --- Filter out drafted players, then recalculate live PAR for the current board ---
available_players = players_df[
    ~players_df["player_normalized"].isin(st.session_state.drafted_normalized)
].drop(columns=["par"])

# players_df already has "predicted_diff"; drop the stale static "par" above and
# recompute a live one that reflects who's actually still on the board.
available_players = recalculate_par(available_players)

# --- Best value picks: factors in position need, PAR, points, and predicted_diff ---
st.subheader("💎 Best Value Picks for Your Team")
needed_positions = compute_position_needs(st.session_state.my_roster)

if available_players.empty:
    st.write("No available players found.")
else:
    scored = available_players.copy()
    scored["par_norm"] = normalize_series(scored["par"])
    scored["fantpt_norm"] = normalize_series(scored["avg_fantpt"])
    scored["diff_norm"] = normalize_series(scored["predicted_diff"])
    scored["score"] = (
        w_par_n * scored["par_norm"] + w_pts_n * scored["fantpt_norm"] + w_diff_n * scored["diff_norm"]
    )

    if not needed_positions:
        st.write("Your starting lineup and FLEX are full — nice work! Check the tables below for bench depth.")
        candidates = scored.sort_values(by="score", ascending=False).head(10)
    else:
        candidates = scored[scored["Position"].isin(needed_positions)].sort_values(by="score", ascending=False)

    if not candidates.empty:
        top_rec = candidates.iloc[0]
        st.write(
            f"🔥 **Top recommendation: {top_rec['player']} ({top_rec['Position']})** — "
            f"best blend of positional drop-off, projected points, and projected diff among the positions you still need."
        )
        st.dataframe(
            candidates[["Position", "player", "avg_fantpt", "par", "predicted_diff", "score"]].head(10),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No available players found at the positions you still need.")

# --- Display Top Pick by Position ---
st.subheader("🔝 Best Available Pick by Position")

top_picks = []

for position in ["QB", "RB", "WR", "TE"]:
    top_player = (
        available_players[available_players["Position"] == position]
        .sort_values(by="avg_fantpt", ascending=False)
        .head(1)
    )
    if not top_player.empty:
        top_picks.append(top_player)

if top_picks:
    top_picks_df = pd.concat(top_picks)
    st.dataframe(
        top_picks_df[["Position", "player", "avg_fantpt", "par", "predicted_diff"]],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.write("No available players to show.")


# --- Display Top 5 by Position ---
st.subheader("🎯 Top 5 Available Players by Position")

for position in ["QB", "RB", "WR", "TE"]:
    st.markdown(f"### {position}")
    top5 = (
        available_players[available_players["Position"] == position]
        .sort_values(by="avg_fantpt", ascending=False)
        .head(5)
    )
    st.dataframe(top5[["player", "avg_fantpt", "par", "predicted_diff"]], use_container_width=True, hide_index=True)

# --- My Team (moved to the bottom so recommendations stay visible while drafting) ---
st.divider()
st.subheader("🧑‍💼 My Team")
roster_rows = [
    {
        "Slot": slot["label"],
        "Player": slot["player"] if slot["player"] else "—",
        "Position": slot["position"] if slot["position"] else "",
        "Avg FantPt": slot["avg_fantpt"] if slot["avg_fantpt"] is not None else "",
        "PAR": slot["par"] if slot["par"] is not None else "",
        "Projected Diff": slot["predicted_diff"] if slot["predicted_diff"] is not None else "",
    }
    for slot in st.session_state.my_roster
]
st.dataframe(pd.DataFrame(roster_rows), use_container_width=True, hide_index=True)

filled_slots = [s for s in st.session_state.my_roster if s["player"] is not None]
total_fantpt = sum(s["avg_fantpt"] for s in filled_slots if s["avg_fantpt"] is not None)
total_par = sum(s["par"] for s in filled_slots if s["par"] is not None)
total_diff = sum(s["predicted_diff"] for s in filled_slots if s["predicted_diff"] is not None)

sum_col1, sum_col2, sum_col3 = st.columns(3)
sum_col1.metric("Total Avg FantPt", f"{total_fantpt:.1f}")
sum_col2.metric("Total PAR", f"{total_par:.1f}")
sum_col3.metric("Total Projected Diff", f"{total_diff:.1f}")
