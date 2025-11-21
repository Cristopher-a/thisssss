from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from supabase import create_client, Client

# ----------------------------
# Configuración Supabase
# ----------------------------
SUPABASE_URL = "https://rhttqmtzcmwilzshnxwq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJodHRxbXR6Y213aWx6c2hueHdxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM1OTUwOTAsImV4cCI6MjA3OTE3MTA5MH0.8dYvM8CBEdqiF9ZZhaYRKhtOin_wYGf4JYrmTTIsX74"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------
# Configuración Flask
# ----------------------------
app = Flask(__name__)
CORS(app)

# ----------------------------
# Único endpoint con TODO adentro
# ----------------------------
@app.route("/")
def hello():
    return "Hello World!"

@app.route("/ranking", methods=["POST"])
def get_ranking():

    # 1️⃣ Obtener eventCode del JSON
    data = request.get_json()
    eventCode = data.get("eventCode")
    if not eventCode:
        return jsonify({"error": "No se proporcionó eventCode"}), 400

    try:
        # 2️⃣ Traer datos desde Supabase
        pits_data = supabase.table("pits").select("*").execute().data
        matches_data = supabase.table("matches").select("*").execute().data

        if not pits_data or not matches_data:
            return jsonify([])

        df_pits = pd.DataFrame(pits_data)
        df_matches = pd.DataFrame(matches_data)

        # 3️⃣ Unir pits + matches
        df = pd.merge(
            df_matches,
            df_pits,
            how="left",
            left_on=["team_number", "regional"],
            right_on=["team_number", "region"]
        )

        if "region" in df.columns:
            df = df.drop(columns=["region"])

        # 4️⃣ Columnas numéricas (incluye las nuevas)
        score_cols = [
            'check_inicio', 'count_motiv', 
            'count_in_cage_auto', 'count_out_cage_auto',
            'count_in_cage_teleop', 'count_out_cage_teleop',
            'count_rp', 'check_scoring',
            'count_in_cage_endgame', 'count_out_cage_endgame',
            'check_full_park', 'check_partial_park', 'check_high',

            # Nuevas columnas
            'cycle_number',
            'artifacts_number',
            'check1'
        ]

        # Convertir a numérico
        for col in score_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # 5️⃣ Score total
        df["score"] = df[score_cols].sum(axis=1)

        # 6️⃣ Agrupar por equipo
        team_stats = df.groupby("team_number").agg({
            "score": "mean",
            "count_in_cage_auto": "sum",
            "count_in_cage_teleop": "sum"
        }).reset_index()

        team_stats["score"] = team_stats["score"].round(2)

        # 7️⃣ Obtener ranking FTC por equipo directo en el endpoint
        def get_ftc_rank(team):
            url = f"http://ftc-api.firstinspires.org/v2.0/2024/rankings/{eventCode}"
            username = "crisesv4"
            password = "E936A6EC-14B0-4904-8DF4-E4916CA4E9BB"
            try:
                r = requests.get(url, auth=HTTPBasicAuth(username, password))
                r.raise_for_status()
                data = r.json()
                rankings = data.get("rankings")
                if not rankings:
                    return None
                for item in rankings:
                    if item.get("teamNumber") == team:
                        return item.get("rank")
                return None
            except:
                return None

        team_stats["ftc_rank"] = team_stats["team_number"].apply(get_ftc_rank)

        # 8️⃣ Calcular alliance_score
        team_stats["efficiency"] = (
            team_stats["count_in_cage_auto"] +
            team_stats["count_in_cage_teleop"]
        ) / (team_stats["score"] + 1)

        team_stats["ftc_rank_score"] = team_stats["ftc_rank"].apply(
            lambda x: 1/x if x else 0
        )

        team_stats["alliance_score"] = (
            team_stats["score"] * 0.6 +
            team_stats["efficiency"] * 0.3 +
            team_stats["ftc_rank_score"] * 0.1
        )

        # 9️⃣ Ordenar y devolver
        df_final = team_stats.sort_values("alliance_score", ascending=False)

        return jsonify(df_final.to_dict(orient="records"))

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------------------
# Correr Flask
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
