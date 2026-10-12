import os
import json
from datetime import datetime
from tools.mongodb_mcp import extract_mcp_data, ensure_connected, mcp_error
import requests

ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary"

async def save_prediction(session, user_id: str, match_id: str, home_team: str, away_team: str,
                          predicted_home_score: int, predicted_away_score: int, match_date: str = None):
    await ensure_connected(session)
    try:
        if predicted_home_score > predicted_away_score:
            predicted_winner = home_team
        elif predicted_away_score > predicted_home_score:
            predicted_winner = away_team
        else:
            predicted_winner = "Draw"

        # Upsert pattern: delete any existing prediction for this user+match, then insert
        del_result = await session.call_tool("delete-many", {
            "database": "wc2026",
            "collection": "predictions",
            "filter": {"user_id": user_id, "match_id": match_id}
        })

        err = mcp_error(del_result)
        if err:
            print(f"  save_prediction failed (clearing old pick): {err}")
            return f"Failed to save prediction for {home_team} vs {away_team}: {err}"

        result = await session.call_tool("insert-many", {
            "database": "wc2026",
            "collection": "predictions",
            "documents": [{
                "user_id": user_id,
                "match_id": match_id,
                "home_team": home_team,
                "away_team": away_team,
                "match_date": match_date,
                "predicted_home_score": predicted_home_score,
                "predicted_away_score": predicted_away_score,
                "predicted_winner": predicted_winner,
                "actual_home_score": None,
                "actual_away_score": None,
                "result_status": "pending",
                "points": 0,
                "created_at": datetime.utcnow().isoformat()
            }]
        })
        err = mcp_error(result)
        if err:
            print(f"  save_prediction failed: {err}")
            return f"Failed to save prediction for {home_team} vs {away_team}: {err}"
        print(f"  save_prediction result: {result.content[0].text if result.content else 'no content'}")
        return f"Prediction saved: {home_team} {predicted_home_score}-{predicted_away_score} {away_team} (you picked {predicted_winner} to win)"
    except Exception as e:
        print(f"  save_prediction error: {e}")
        return f"Error saving prediction: {e}"


async def get_predictions(session, user_id: str, status: str = "all"):
    filter_q = {"user_id": user_id}
    if status == "pending":
        filter_q["result_status"] = "pending"
    elif status == "completed":
        filter_q["result_status"] = {"$ne": "pending"}

    result = await session.call_tool("find", {
        "database": "wc2026",
        "collection": "predictions",
        "filter": filter_q
    })
    err = mcp_error(result)
    if err:
        return {"predictions": [], "error": err}
    docs = extract_mcp_data(result)
    return {"predictions": docs if isinstance(docs, list) else []}


async def delete_prediction(session, user_id: str, match_id: str):
    await ensure_connected(session)
    try:
        result = await session.call_tool("delete-many", {
            "database": "wc2026",
            "collection": "predictions",
            "filter": {"user_id": user_id, "match_id": match_id}
        })
        err = mcp_error(result)
        if err:
            print(f"  delete_prediction failed: {err}")
            return f"Failed to delete prediction: {err}"
        print(f"  delete_prediction result: {result.content[0].text if result.content else 'no content'}")
        return f"Prediction deleted"
    except Exception as e:
        print(f"  delete_prediction error: {e}")
        return f"Error deleting prediction: {e}"
    

def fetch_match_result(match_id: str):
    """Fetch actual result for a finished match from ESPN."""
    try:
        r = requests.get(ESPN_SUMMARY, params={"event": match_id}, timeout=10)
        data = r.json()
        header = data.get("header", {})
        competitions = header.get("competitions", [{}])[0]
        competitors = competitions.get("competitors", [])
        status = header.get("competitions", [{}])[0].get("status", {}).get("type", {}).get("description", "")

        if status not in ("Final", "FT", "Full Time"):
            return None

        scores = {}
        for c in competitors:
            team_name = c.get("team", {}).get("displayName", "")
            home_away = c.get("homeAway", "")
            score = int(c.get("score", 0))
            scores[home_away] = {"team": team_name, "score": score}

        return scores
    except Exception as e:
        print(f"  fetch_match_result error: {e}")
        return None


def calculate_points(predicted_home: int, predicted_away: int, actual_home: int, actual_away: int):
    """3 points for exact score, 1 point for correct winner, 0 for wrong."""
    if predicted_home == actual_home and predicted_away == actual_away:
        return 3, "exact"
    
    predicted_winner = "home" if predicted_home > predicted_away else ("away" if predicted_away > predicted_home else "draw")
    actual_winner = "home" if actual_home > actual_away else ("away" if actual_away > actual_home else "draw")
    
    if predicted_winner == actual_winner:
        return 1, "winner"
    return 0, "wrong"


async def score_predictions(session, user_id: str):
    """Score pending predictions. Uses ESPN results if available, falls back to manually set actual scores in DB."""
    await ensure_connected(session)
    
    result = await session.call_tool("find", {
        "database": "wc2026",
        "collection": "predictions",
        "filter": {"user_id": user_id, "result_status": "pending"}
    })
    err = mcp_error(result)
    if err:
        return {"updated": 0, "total_points_earned": 0, "breakdown": [], "error": err}
    pending = extract_mcp_data(result)
    
    if not pending:
        return {"updated": 0, "message": "No pending predictions to score"}
    
    updated_count = 0
    total_points = 0
    breakdown = []
    
    for pred in pending:
        # Try ESPN first
        match_result = fetch_match_result(pred["match_id"])
        
        if match_result:
            actual_home = match_result.get("home", {}).get("score", 0)
            actual_away = match_result.get("away", {}).get("score", 0)
        elif pred.get("actual_home_score") is not None and pred.get("actual_away_score") is not None:
            # Fall back to manually set scores in DB (for testing or manual entry)
            actual_home = pred["actual_home_score"]
            actual_away = pred["actual_away_score"]
        else:
            continue
        
        points, status = calculate_points(
            pred["predicted_home_score"], pred["predicted_away_score"],
            actual_home, actual_away
        )
        
        update_result = await session.call_tool("update-many", {
            "database": "wc2026",
            "collection": "predictions",
            "filter": {"user_id": user_id, "match_id": pred["match_id"]},
            "update": {"$set": {
                "actual_home_score": actual_home,
                "actual_away_score": actual_away,
                "result_status": status,
                "points": points
            }}
        })
        
        updated_count += 1
        total_points += points
        breakdown.append({
            "match": f"{pred['home_team']} vs {pred['away_team']}",
            "predicted": f"{pred['predicted_home_score']}-{pred['predicted_away_score']}",
            "actual": f"{actual_home}-{actual_away}",
            "result": status,
            "points": points
        })
        if mcp_error(update_result):
            print(f"  score_predictions: failed to update {pred['match_id']}: {mcp_error(update_result)}")
            continue
    
    return {
        "updated": updated_count,
        "total_points_earned": total_points,
        "breakdown": breakdown
    }


async def get_leaderboard(session, limit: int = 10):
    """Aggregate predictions by user and return top scorers."""
    try:
        result = await session.call_tool("aggregate", {
            "database": "wc2026",
            "collection": "predictions",
            "pipeline": [
                {"$match": {"result_status": {"$ne": "pending"}}},
                {"$group": {
                    "_id": "$user_id",
                    "total_points": {"$sum": "$points"},
                    "predictions_scored": {"$sum": 1},
                    "exact_predictions": {
                        "$sum": {"$cond": [{"$eq": ["$result_status", "exact"]}, 1, 0]}
                    }
                }},
                {"$sort": {"total_points": -1}},
                {"$limit": limit}
            ]
        })
        err = mcp_error(result)
        if err:
            return {"leaderboard": [], "error": err}
        docs = extract_mcp_data(result)
        leaderboard = []
        for entry in docs:
            leaderboard.append({
                "user_id": entry.get("_id"),
                "total_points": entry.get("total_points", 0),
                "predictions": entry.get("predictions_scored", 0),
                "exact_predictions": entry.get("exact_predictions", 0)
            })
        return {"leaderboard": leaderboard}
    except Exception as e:
        print(f"  get_leaderboard error: {e}")
        return {"leaderboard": [], "error": str(e)}