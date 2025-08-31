import streamlit as st
import pandas as pd
import re

# --- Helper function to normalize names ---
def normalize_name(name):
    return re.sub(r'[^a-z]', '', name.lower())  # remove non-letters, lowercase

# --- Load Data ---
@st.cache_data
def load_data():
    qb = pd.read_csv("qb_predictions25.csv")
    rb = pd.read_csv("rb_predictions25.csv")
    wr = pd.read_csv("wr_predictions25.csv")
    te = pd.read_csv("te_predictions25.csv")
    
    # Shift the 'par' column upward by 1 for each position dataset
    qb['par'] = qb['par'].shift(-1)
    rb['par'] = rb['par'].shift(-1)
    wr['par'] = wr['par'].shift(-1)
    te['par'] = te['par'].shift(-1)

    qb["Position"] = "QB"
    rb["Position"] = "RB"
    wr["Position"] = "WR"
    te["Position"] = "TE"

    df = pd.concat([qb, rb, wr, te], ignore_index=True)

    # Add normalized player name for case- and punctuation-insensitive lookup
    df["player_normalized"] = df["player"].apply(normalize_name)

    return df

players_df = load_data()

# --- Track drafted players ---
if "drafted_normalized" not in st.session_state:
    st.session_state.drafted_normalized = set()


# --- Streamlit App UI ---
st.title("🏈 Fantasy Football Draft Tool")

# --- Input form with Enter key support and auto-clear ---
with st.form("draft_form", clear_on_submit=True):
    player_drafted = st.text_input(
        "Enter drafted player name:",
        key="player_input"
    )
    submitted = st.form_submit_button("Add Pick")

if submitted:
    if player_drafted:
        normalized_input = normalize_name(player_drafted)
        if normalized_input in players_df["player_normalized"].values:
            st.session_state.drafted_normalized.add(normalized_input)
            st.success(f"{player_drafted} marked as drafted.")
        else:
            st.warning(f"No match found for '{player_drafted}'. Please check spelling.")


# --- Filter available players ---
available_players = players_df[
    ~players_df["player_normalized"].isin(st.session_state.drafted_normalized)
]

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


st.subheader("🎯 Top 5 Available Players by Position")

for position in ["QB", "RB", "WR", "TE"]:
    st.markdown(f"### {position}")
    top5 = (
        available_players[available_players["Position"] == position]
        .sort_values(by="avg_fantpt", ascending=False)
        .head(5)
    )
    # Display the table with relevant columns
    st.dataframe(top5[["player", "avg_fantpt", "par"]])

