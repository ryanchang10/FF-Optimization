import streamlit as st
import pandas as pd
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

    # Add normalized player name for lookup
    df["player_normalized"] = df["player"].apply(normalize_name)

    return df


# --- Recalculate PAR (drop-off to next best player) dynamically ---
def recalculate_par(df):
    updated = []

    for position in ["QB", "RB", "WR", "TE"]:
        pos_df = df[df["Position"] == position].copy()
        pos_df = pos_df.sort_values(by="avg_fantpt", ascending=False).reset_index(drop=True)
        pos_df["par"] = pos_df["avg_fantpt"] - pos_df["avg_fantpt"].shift(-1)
        updated.append(pos_df)

    return pd.concat(updated, ignore_index=True)


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
def fill_roster_slot(roster, position, player_name, avg_fantpt):
    def try_fill(slot_type):
        for slot in roster:
            if slot["slot_type"] == slot_type and slot["player"] is None:
                slot["player"] = player_name
                slot["position"] = position
                slot["avg_fantpt"] = avg_fantpt
                return True
        return False

    if position == "QB":
        return try_fill("QB") or try_fill("BENCH")

    if position in ("RB", "WR", "TE"):
        return try_fill(position) or try_fill("FLEX") or try_fill("BENCH")

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
            fill_roster_slot(roster, entry["position"], entry["player"], entry["avg_fantpt"])

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


# --- Load the full dataset ---
players_df = load_data()

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

# --- Sidebar: league info + reset ---
with st.sidebar:
    st.markdown("### League Setup")
    st.write(f"Teams: **{config['num_teams']}**")
    st.write(f"Your draft slot: **{config['draft_slot']}**")
    st.write(f"Picks logged so far: **{st.session_state.pick_count}**")
    if st.button("🔄 Reset Draft"):
        for key in ["league_config", "my_roster", "drafted_normalized", "pick_count", "draft_log"]:
            st.session_state.pop(key, None)
        st.rerun()

# --- Whose turn is it? ---
next_pick_number = st.session_state.pick_count + 1
on_the_clock = team_on_the_clock(next_pick_number, config["num_teams"])
is_my_turn = on_the_clock == config["draft_slot"]

if is_my_turn:
    st.info(f"📢 Pick #{next_pick_number} — **You're on the clock!**")
else:
    st.write(f"Pick #{next_pick_number} — Team {on_the_clock} on the clock")

# --- Input form with Enter key support and auto-clear ---
with st.form("draft_form", clear_on_submit=True):
    player_drafted = st.text_input(
        "Enter drafted player name:",
        key="player_input"
    )
    submitted = st.form_submit_button("Add Pick")

if submitted and player_drafted:
    normalized_input = normalize_name(player_drafted)

    if normalized_input in st.session_state.drafted_normalized:
        st.warning(f"{player_drafted} has already been marked as drafted.")
    elif normalized_input in players_df["player_normalized"].values:
        match = players_df[players_df["player_normalized"] == normalized_input].iloc[0]
        entry = {
            "player": match["player"],
            "position": match["Position"],
            "avg_fantpt": match["avg_fantpt"],
            "normalized": normalized_input,
        }
        st.session_state.draft_log.append(entry)
        rebuild_state()
        pick_num = len(st.session_state.draft_log)
        landed_on_team = " — added to your roster!" if team_on_the_clock(pick_num, config["num_teams"]) == config["draft_slot"] else ""
        st.success(f"Pick #{pick_num}: {match['player']} ({match['Position']}){landed_on_team}")
    else:
        st.warning(f"No match found for '{player_drafted}'. Please check spelling.")

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
            {"Pick #": i + 1, "Player": e["player"], "Position": e["position"], "Avg FantPt": e["avg_fantpt"]}
            for i, e in enumerate(log)
        ])
        st.dataframe(log_df, use_container_width=True, hide_index=True)

# --- Filter out drafted players ---
available_players = players_df[
    ~players_df["player_normalized"].isin(st.session_state.drafted_normalized)
]

# --- Recalculate PAR values dynamically ---
available_players = recalculate_par(available_players)

# --- Display My Team ---
st.subheader("🧑‍💼 My Team")
roster_rows = [
    {
        "Slot": slot["label"],
        "Player": slot["player"] if slot["player"] else "—",
        "Position": slot["position"] if slot["position"] else "",
        "Avg FantPt": slot["avg_fantpt"] if slot["avg_fantpt"] is not None else "",
    }
    for slot in st.session_state.my_roster
]
st.dataframe(pd.DataFrame(roster_rows), use_container_width=True, hide_index=True)

# --- Best value picks based on your team's needs ---
st.subheader("💎 Best Value Picks for Your Team")
needed_positions = compute_position_needs(st.session_state.my_roster)

if not needed_positions:
    st.write("Your starting lineup and FLEX are full — nice work! Check the tables below for bench depth.")
else:
    need_candidates = []
    for position in needed_positions:
        top_at_pos = (
            available_players[available_players["Position"] == position]
            .sort_values(by="avg_fantpt", ascending=False)
            .head(1)
        )
        if not top_at_pos.empty:
            need_candidates.append(top_at_pos)

    if need_candidates:
        need_df = pd.concat(need_candidates).sort_values(by="par", ascending=False)
        top_rec = need_df.iloc[0]
        st.write(
            f"🔥 **Top recommendation: {top_rec['player']} ({top_rec['Position']})** — "
            f"biggest drop-off before the next best option at a position you still need."
        )
        st.dataframe(need_df[["Position", "player", "avg_fantpt", "par"]], use_container_width=True, hide_index=True)
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
    st.dataframe(top_picks_df[["Position", "player", "avg_fantpt", "par"]])
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
    st.dataframe(top5[["player", "avg_fantpt", "par"]])
