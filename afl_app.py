import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import os
import re
import base64
from datetime import datetime

# ── Paths — relative so the app works locally and on Streamlit Cloud ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'afl.db')
LOGO_DIR = os.path.join(BASE_DIR, 'logos')
BG_PATH  = os.path.join(BASE_DIR, 'background_light.svg')

def _load_bg_css():
    if os.path.exists(BG_PATH):
        with open(BG_PATH, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode()
        url = f'data:image/svg+xml;base64,{b64}'
        return (
            f'.stApp {{'
            f'background-image: url("{url}") !important;'
            f'background-size: cover !important;'
            f'background-attachment: fixed !important;'
            f'background-repeat: no-repeat !important;'
            f'background-position: center !important;'
            f'}}'
        )
    return ''

st.set_page_config(
    page_title='AFL Statistics',
    page_icon='🏉',
    layout='wide'
)

st.markdown(f"""
    <style>
    {_load_bg_css()}
    .block-container {{ padding-top: 2.5rem; padding-bottom: 0rem; }}
    h1 {{ font-size: 1.6rem; margin-bottom: 0; color: #003087; }}
    h3 {{ font-size: 1rem; margin-top: 0.3rem; color: #444; }}
    .stMetric {{ padding: 0.1rem 0; }}
    .stMetric label {{ font-size: 0.72rem !important; }}
    .stMetric [data-testid="stMetricValue"] {{ font-size: 1rem !important; }}
    div[data-testid="stVerticalBlock"] {{ gap: 0.25rem; }}
    hr {{ margin: 0.3rem 0; }}
    footer {{ visibility: hidden; }}
    </style>
""", unsafe_allow_html=True)

# ─── HELPERS ──────────────────────────────────────────────────────
def parse_game_date(date_str):
    if not date_str:
        return datetime(1900, 1, 1)
    m = re.search(r'(\d+)-(\w+)-(\d{4})', str(date_str))
    if m:
        try:
            return datetime.strptime(
                f'{m.group(1)}-{m.group(2)}-{m.group(3)}', '%d-%b-%Y'
            )
        except Exception:
            pass
    return datetime(1900, 1, 1)

def format_date(date_str):
    if not date_str:
        return '–'
    m = re.search(r'\d+-\w+-\d{4}', str(date_str))
    return m.group(0) if m else str(date_str)

def score_str(goals, behinds, total):
    try:
        if pd.notna(goals) and pd.notna(behinds):
            return f'{int(goals)}.{int(behinds)} ({int(total)})'
        elif pd.notna(total) and total > 0:
            return f'– ({int(total)})'
        return '–'
    except Exception:
        return '–'

TEAM_COLOURS = {
    'Adelaide':               '#002B5C',
    'Brisbane Lions':         '#A30046',
    'Carlton':                '#0E1A2B',
    'Collingwood':            '#000000',
    'Essendon':               '#CC2031',
    'Fitzroy':                '#A4003B',
    'Footscray':              '#014896',
    'Fremantle':              '#2C1654',
    'Geelong':                '#1C3C6E',
    'Gold Coast':             '#E3272A',
    'Greater Western Sydney': '#F47920',
    'Hawthorn':               '#4D2004',
    'Kangaroos':              '#003087',
    'Melbourne':              '#CC2031',
    'North Melbourne':        '#003087',
    'Port Adelaide':          '#008AAB',
    'Richmond':               '#FFD200',
    'St Kilda':               '#ED0F05',
    'Sydney':                 '#ED171F',
    'Tasmania':               '#003087',
    'University':             '#0057A8',
    'West Coast':             '#062E6F',
    'Western Bulldogs':       '#014896',
    'Brisbane Bears':         '#8B0000',
}

def team_colour(team):
    return TEAM_COLOURS.get(team, '#003087')

# ─── DATABASE ─────────────────────────────────────────────────────
@st.cache_data
def get_teams():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql(
        'SELECT DISTINCT team FROM game_teams ORDER BY team', conn
    )
    conn.close()
    return ['— Select a team —'] + df['team'].tolist()

@st.cache_data
def get_all_logos():
    path_map = {}
    if not os.path.exists(LOGO_DIR):
        return path_map
    for f in os.listdir(LOGO_DIR):
        if f.endswith('.png'):
            team = f.replace('.png', '').replace('_', ' ')
            path_map[team] = os.path.join(LOGO_DIR, f)
    return path_map

@st.cache_data
def get_results(team):
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql('''
        SELECT
            g.game_id,
            g.year,
            g.round,
            g.date,
            g.venue,
            g.attendance,
            gt.score             AS team_score,
            gt.is_winner,
            opp.team             AS opponent,
            opp.score            AS opponent_score,
            gt.score - opp.score AS margin,
            CASE
                WHEN gt.is_winner = 1     THEN 'Win'
                WHEN gt.score = opp.score THEN 'Draw'
                ELSE 'Loss'
            END AS result
        FROM games g
        JOIN game_teams gt  ON g.game_id = gt.game_id  AND gt.team  = ?
        JOIN game_teams opp ON g.game_id = opp.game_id AND opp.team != gt.team
    ''', conn, params=[team])
    conn.close()
    df['_sort_date'] = df['date'].apply(parse_game_date)
    df = df.sort_values('_sort_date', ascending=False).drop('_sort_date', axis=1)
    return df.reset_index(drop=True)

@st.cache_data
def get_score_breakdown(team, game_ids):
    if not game_ids:
        return pd.DataFrame(), pd.DataFrame()
    conn = sqlite3.connect(DB_PATH)
    ph = ','.join(['?'] * len(game_ids))

    # Primary: sum from player_stats
    team_df = pd.read_sql(f'''
        SELECT game_id, SUM(goals) AS goals, SUM(behinds) AS behinds
        FROM player_stats
        WHERE game_id IN ({ph}) AND team = ? AND goals IS NOT NULL
        GROUP BY game_id
    ''', conn, params=game_ids + [team])

    opp_df = pd.read_sql(f'''
        SELECT game_id, SUM(goals) AS opp_goals, SUM(behinds) AS opp_behinds
        FROM player_stats
        WHERE game_id IN ({ph}) AND team != ? AND goals IS NOT NULL
        GROUP BY game_id
    ''', conn, params=game_ids + [team])

    # Fallback: game_teams goals/behinds for any still missing
    gt_team = pd.read_sql(f'''
        SELECT game_id, goals, behinds FROM game_teams
        WHERE game_id IN ({ph}) AND team = ? AND goals IS NOT NULL
    ''', conn, params=game_ids + [team])

    gt_opp = pd.read_sql(f'''
        SELECT game_id, goals AS opp_goals, behinds AS opp_behinds
        FROM game_teams
        WHERE game_id IN ({ph}) AND team != ? AND goals IS NOT NULL
    ''', conn, params=game_ids + [team])

    conn.close()

    if not gt_team.empty:
        missing = set(gt_team['game_id']) - set(team_df['game_id'])
        if missing:
            team_df = pd.concat([
                team_df,
                gt_team[gt_team['game_id'].isin(missing)]
            ], ignore_index=True)

    if not gt_opp.empty:
        missing = set(gt_opp['game_id']) - set(opp_df['game_id'])
        if missing:
            opp_df = pd.concat([
                opp_df,
                gt_opp[gt_opp['game_id'].isin(missing)]
            ], ignore_index=True)

    return team_df, opp_df

# ─── LOAD DATA ────────────────────────────────────────────────────
teams     = get_teams()
all_logos = get_all_logos()

# ─── HEADER ───────────────────────────────────────────────────────
hdr_title, hdr_selector = st.columns([3, 2])

with hdr_title:
    st.markdown('# 🏉 AFL Statistics Dashboard')
    st.markdown(
        '<small>Data sourced from '
        '<a href="https://afltables.com" target="_blank">AFL Tables</a>'
        '</small>',
        unsafe_allow_html=True
    )

with hdr_selector:
    st.markdown('<br>', unsafe_allow_html=True)
    sel_row = st.columns([1, 5])
    with sel_row[0]:
        logo_placeholder = st.empty()
    with sel_row[1]:
        selected_team = st.selectbox(
            'Select Team',
            teams,
            index=0
        )
    if selected_team and selected_team != '— Select a team —':
        logo = all_logos.get(selected_team)
        if logo and os.path.exists(logo):
            logo_placeholder.image(logo, width=55)

st.divider()

# ─── MAIN LAYOUT ──────────────────────────────────────────────────
left_col, right_col = st.columns([2, 3])

with left_col:

    if not selected_team or selected_team == '— Select a team —':
        st.markdown(
            '<br><br>'
            '<p style="color:#bbb; text-align:center; font-size:1.1rem">'
            '← Select a team above to get started'
            '</p>',
            unsafe_allow_html=True
        )

    else:
        all_results = get_results(selected_team)
        colour      = team_colour(selected_team)

        min_year = int(all_results['year'].min()) if not all_results.empty else 1897
        max_year = int(all_results['year'].max()) if not all_results.empty else 2026

        st.markdown('### Filters')
        st.markdown('<small><b>Year range</b></small>', unsafe_allow_html=True)

        yr_a, yr_b = st.columns(2)
        with yr_a:
            from_year = st.number_input(
                'From', min_value=min_year, max_value=max_year,
                value=min_year, step=1
            )
        with yr_b:
            to_year = st.number_input(
                'To', min_value=min_year, max_value=max_year,
                value=max_year, step=1
            )

        if from_year > to_year:
            from_year, to_year = to_year, from_year

        year_range = st.slider(
            'Year slider', min_value=min_year, max_value=max_year,
            value=(int(from_year), int(to_year)), step=1,
            label_visibility='collapsed'
        )
        effective_from, effective_to = year_range

        year_filtered = all_results[
            (all_results['year'] >= effective_from) &
            (all_results['year'] <= effective_to)
        ]

        all_opponents = sorted(year_filtered['opponent'].unique().tolist())
        selected_opponents = st.multiselect(
            'Opponent (leave blank for all)', all_opponents, default=[]
        )

        filtered = (
            year_filtered[year_filtered['opponent'].isin(selected_opponents)]
            if selected_opponents else year_filtered.copy()
        )

        available_venues = sorted(filtered['venue'].dropna().unique().tolist())
        selected_venues = st.multiselect(
            'Venue (leave blank for all)', available_venues, default=[]
        )
        if selected_venues:
            filtered = filtered[filtered['venue'].isin(selected_venues)]

        if selected_opponents:
            st.markdown('<small><b>Selected opponents:</b></small>',
                        unsafe_allow_html=True)
            logo_cols = st.columns(min(len(selected_opponents), 6))
            for i, opp in enumerate(selected_opponents):
                opp_logo = all_logos.get(opp)
                with logo_cols[i % 6]:
                    if opp_logo and os.path.exists(opp_logo):
                        st.image(opp_logo, width=40)
                    st.markdown(
                        f'<small style="font-size:0.6rem">{opp}</small>',
                        unsafe_allow_html=True
                    )

        st.divider()

        wins   = len(filtered[filtered['result'] == 'Win'])
        losses = len(filtered[filtered['result'] == 'Loss'])
        draws  = len(filtered[filtered['result'] == 'Draw'])
        total  = len(filtered)
        win_pct = round(wins / total * 100, 1) if total > 0 else 0

        st.markdown(f'### {selected_team} — Summary')

        labels, values, colours = [], [], []
        if wins   > 0: labels.append('Win');  values.append(wins);   colours.append(colour)
        if losses > 0: labels.append('Loss'); values.append(losses); colours.append('#CCCCCC')
        if draws  > 0: labels.append('Draw'); values.append(draws);  colours.append('#FFD200')

        fig = go.Figure(data=[go.Pie(
            labels=labels, values=values, hole=0.42,
            marker=dict(colors=colours),
            textinfo='label+percent',
            hovertemplate='%{label}: %{value} games (%{percent})<extra></extra>'
        )])
        fig.update_layout(
            showlegend=True,
            legend=dict(orientation='h', y=-0.1),
            margin=dict(t=5, b=5, l=5, r=5),
            height=210,
            annotations=[dict(
                text=f'<b>{win_pct}%</b>', x=0.5, y=0.5,
                font_size=18, font_color=colour, showarrow=False
            )]
        )
        st.plotly_chart(fig, use_container_width=True)

        m1, m2, m3 = st.columns(3)
        m1.metric('Games',  total)
        m2.metric('Wins',   wins)
        m3.metric('Losses', losses)

        avg_margin = round(filtered['margin'].mean(), 1) if total > 0 else 0
        avg_win    = round(filtered[filtered['result']=='Win']['margin'].mean(),  1) if wins   > 0 else 0
        avg_loss   = round(filtered[filtered['result']=='Loss']['margin'].mean(), 1) if losses > 0 else 0

        m4, m5, m6 = st.columns(3)
        m4.metric('Avg Margin', f'{avg_margin:+.1f}')
        m5.metric('Avg Win',    f'+{avg_win}')
        m6.metric('Avg Loss',   f'{avg_loss:.1f}')

        st.divider()

        wins_df   = filtered[filtered['result'] == 'Win'].nlargest(5, 'margin')
        losses_df = filtered[filtered['result'] == 'Loss'].nsmallest(5, 'margin')

        st.markdown('**Top 5 biggest wins**')
        if not wins_df.empty:
            for _, r in wins_df.iterrows():
                st.markdown(
                    f'<small>+{int(r["margin"])} &nbsp;·&nbsp; '
                    f'{format_date(r["date"])} &nbsp;·&nbsp; '
                    f'vs {r["opponent"]}</small>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown('<small>No wins in selected range</small>',
                        unsafe_allow_html=True)

        st.markdown('**Top 5 biggest losses**')
        if not losses_df.empty:
            for _, r in losses_df.iterrows():
                st.markdown(
                    f'<small>{int(r["margin"])} &nbsp;·&nbsp; '
                    f'{format_date(r["date"])} &nbsp;·&nbsp; '
                    f'vs {r["opponent"]}</small>',
                    unsafe_allow_html=True
                )
        else:
            st.markdown('<small>No losses in selected range</small>',
                        unsafe_allow_html=True)

        st.divider()

        streak_result = None
        streak_count  = 0
        for res in filtered['result']:
            if streak_result is None:
                streak_result = res
                streak_count  = 1
            elif res == streak_result:
                streak_count += 1
            else:
                break

        if streak_result and streak_count > 0:
            streak_colour = (
                '#155724' if streak_result == 'Win'
                else '#721c24' if streak_result == 'Loss'
                else '#856404'
            )
            st.markdown(
                f'**Current streak** &nbsp; '
                f'<span style="color:{streak_colour}; font-weight:700">'
                f'{streak_count} {streak_result}'
                f'{"s" if streak_count > 1 else ""}'
                f'</span>',
                unsafe_allow_html=True
            )

with right_col:
    if not selected_team or selected_team == '— Select a team —':
        st.markdown(
            '<div style="text-align:center; margin-top:8rem; color:#bbb">'
            '<p style="font-size:4rem">🏉</p>'
            '<h3 style="color:#bbb">Select a team to view match results</h3>'
            '</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(f'### {selected_team} — Match Results')

        DISPLAY_CAP = 500
        cap_applied = len(filtered) > DISPLAY_CAP
        display_df  = filtered.head(DISPLAY_CAP)

        cap_msg = (
            f'{len(filtered):,} results — most recent {DISPLAY_CAP:,} shown '
            f'(use filters or year range to narrow)'
            if cap_applied else
            f'{len(filtered):,} results — most recent first'
        )
        st.markdown(f'<small>{cap_msg}</small>', unsafe_allow_html=True)

        game_ids = display_df['game_id'].tolist()
        team_scores, opp_scores = get_score_breakdown(selected_team, game_ids)

        display = display_df.copy()

        if not team_scores.empty:
            display = display.merge(team_scores, on='game_id', how='left')
        else:
            display['goals'] = display['behinds'] = None

        if not opp_scores.empty:
            display = display.merge(
                opp_scores[['game_id', 'opp_goals', 'opp_behinds']],
                on='game_id', how='left'
            )
        else:
            display['opp_goals'] = display['opp_behinds'] = None

        display['Team Score'] = display.apply(
            lambda r: score_str(r.get('goals'), r.get('behinds'), r['team_score']),
            axis=1
        )
        display['Opp Score'] = display.apply(
            lambda r: score_str(r.get('opp_goals'), r.get('opp_behinds'), r['opponent_score']),
            axis=1
        )
        display['Margin'] = display['margin'].apply(
            lambda x: f'+{int(x)}' if x > 0 else (str(int(x)) if x < 0 else 'Draw')
        )
        display['Attendance'] = display['attendance'].apply(
            lambda x: f'{int(x):,}' if pd.notna(x) and x > 0 else '–'
        )
        display['Date'] = display['date'].apply(format_date)
        display['Logo'] = display['opponent'].map(lambda x: all_logos.get(x, ''))

        table_df = display[[
            'round', 'Date', 'Logo', 'opponent', 'result',
            'Margin', 'Team Score', 'Opp Score', 'venue', 'Attendance'
        ]].rename(columns={
            'round':    'Round',
            'opponent': 'Opponent',
            'result':   'Result',
            'venue':    'Venue',
        })

        def colour_result(val):
            if val == 'Win':  return 'background-color: #d4edda; color: #155724'
            if val == 'Loss': return 'background-color: #f8d7da; color: #721c24'
            if val == 'Draw': return 'background-color: #fff3cd; color: #856404'
            return ''

        styled = (
            table_df.style
            .map(colour_result, subset=['Result'])
            .set_properties(**{'font-size': '12px', 'text-align': 'left'})
        )

        st.dataframe(
            styled,
            use_container_width=True,
            height=720,
            hide_index=True,
            column_config={
                'Logo':       st.column_config.ImageColumn('',         width='small'),
                'Round':      st.column_config.TextColumn('Round',     width='small'),
                'Date':       st.column_config.TextColumn('Date',      width='medium'),
                'Opponent':   st.column_config.TextColumn('Opponent',  width='medium'),
                'Result':     st.column_config.TextColumn('Result',    width='small'),
                'Margin':     st.column_config.TextColumn('Margin',    width='small'),
                'Team Score': st.column_config.TextColumn('Team',      width='small'),
                'Opp Score':  st.column_config.TextColumn('Opp',       width='small'),
                'Venue':      st.column_config.TextColumn('Venue',     width='medium'),
                'Attendance': st.column_config.TextColumn('Att',       width='small'),
            }
        )

st.divider()
st.markdown(
    '<small>Data: <a href="https://afltables.com" target="_blank">'
    'AFL Tables</a> · Player stats from 1965 · VFL/AFL records from 1897 · '
    'Scores shown as G.B (Total) — "– (T)" indicates breakdown unavailable</small>',
    unsafe_allow_html=True
)
