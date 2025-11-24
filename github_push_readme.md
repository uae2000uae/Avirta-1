# GitHub Push Integration (Admin and Auto Snapshot)

This project includes a built-in GitHub integration to push question JSON files and to automatically upload a snapshot of the questions used in a game when the host clicks End Game.

What exists:
- Admin page action: Push or Sync all contents/questions/*.json files to your repository
- Auto snapshot on End Game: Uploads a JSON file summarizing the game run (players, leaderboard, used questions)

Configuration
1) Open Admin Controls → API Settings and fill in:
   - github_token: a Personal Access Token with repo scope
   - github_repo_owner: e.g., uae2000uae
   - github_repo_name: e.g., Avirta-WebApp
   - github_branch: e.g., Avirta-1 (defaults to main)

2) Save settings.

Admin Push (manual)
- Navigate to /push_questions_to_github (Admin only)
- Choose Push All or Sync
- The service uses GitHub contents API to create/update files.

Auto Snapshot on End Game
- When the host clicks End Game, the app will best-effort push a file to:
  game_runs/<mode>/<room_id>-<YYYYMMDDTHHMMSSZ>.json
- Snapshot includes:
  - room metadata (id, name, host, players)
  - stats (answered_count, total_questions, current_question_number)
  - leaderboard or player_scores
  - questions used (id, type, category_id, question, options, correct_answer, points, source_file, use_count)

Notes
- If GitHub settings are missing/invalid, the game still ends; a notice is flashed and an event is logged.
- For public repositories, consider excluding sensitive data before sharing.
- The integration relies on the GitHub REST v3 contents API.
