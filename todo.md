Change if search querry functionality to use openai right off the bat, don't rely too much on hard coded internal logic

Let's jump into p1, ensure to think about the steps required before implementing any code. Ask me if you need access to API keys, websites, etc. Ensure to implement p1 with scaleability and steps down the road in mind.



Okay, let's consolidate the improvement plan and the brainstormed ideas into a prioritized to-do list, focusing on impact and feasibility for your project. I've also included testing `gpt-4o-mini`.

**Goal:** Improve search result relevance and quality, especially for nuanced queries, by enhancing the data gathering and candidate selection process.

**Prioritized To-Do List:**

1.  **P1: Fix `DataSourceManager` (Web/Reddit Search - Name Extraction):**
    *   **Task:** Implement the basic functionality in `data_sources.py` to perform web searches (e.g., via a library like `requests` + `BeautifulSoup` or a search API if available) and Reddit searches (using PRAW) based on query terms (`amenity`, `location`, `requirements`).
    *   **Goal:** Reliably extract *potential place names* mentioned in search results/discussions related to the user's query.
    *   **Importance:** **CRITICAL BLOCKER.** The entire multi-source funneling strategy depends on having *some* input from these external sources. This is the absolute first step.

2.  **P2: Implement Basic Multi-Source Funnel (Candidate Generation):**
    *   **Task:** Modify the `search` function in `app.py`.
        *   Increase Google Nearby Search results (e.g., fetch 20).
        *   Call the *fixed* `DataSourceManager` (from P1) to get place names from Web/Reddit.
        *   Merge the list of places from Google (with Place IDs) and the names from Web/Reddit.
        *   Deduplicate the list (preferring entries with Place IDs).
        *   Implement basic cross-referencing: Try to find Google Place IDs for names only found via Web/Reddit (using `gmaps.find_place` or similar).
    *   **Goal:** Create a larger, richer pool of candidate places than just the Google Top 5.
    *   **Importance:** **CORE IMPROVEMENT.** Implements the fundamental widening of the initial search net.

3.  **P3: Implement Smarter Ranking (LLM Re-ranking):**
    *   **Task:** Enhance the funnel (Phase 2). After generating the consolidated candidate list, feed the place names (and maybe basic types) along with the user's original query/requirements to `gpt-3.5-turbo`. Ask it to rank these candidates by likely relevance.
    *   **Goal:** Use semantic understanding to prioritize the most promising candidates *before* fetching detailed data.
    *   **Importance:** **HIGH IMPACT.** Significantly improves the quality of candidates selected for the deep dive with relatively low complexity compared to fetching details for all candidates.

4.  **P4: Implement Focused Deep Dive:**
    *   **Task:** Modify the `search` function (Phase 3).
        *   Select the Top N (e.g., 5-7) candidates based on the ranking from P3.
        *   Fetch Google Place Details *only* for these Top N.
        *   (Optional but Recommended) Call `DataSourceManager` again, but this time with *focused* queries for *each* of the Top N places to get specific recent context.
        *   Generate the final analysis prompt using data *only* for these Top N.
    *   **Goal:** Ensure the expensive detail fetching and final analysis steps are performed only on the highest-potential candidates.
    *   **Importance:** **CORE IMPROVEMENT.** Completes the funnel logic and focuses resources.

5.  **P5: Improve Analysis Robustness (Structured JSON Output):**
    *   **Task:** Modify the final analysis prompt (`app.py`) to explicitly instruct the LLM (still `gpt-3.5-turbo` for now) to return its output (summary, highlights, etc.) in a specific JSON format. Update the backend parsing logic to handle JSON directly instead of text splitting.
    *   **Goal:** Make the analysis result processing much more reliable and less prone to breaking if the LLM slightly changes its text formatting.
    *   **Importance:** **MEDIUM (Reliability).** Good practice, improves robustness significantly.

6.  **P6: Optimize Analysis Input (Targeted Snippet Extraction):**
    *   **Task:** Before generating the *final* analysis prompt (in P4), if you're including significant text from Web/Reddit sources, add an intermediate LLM call (`gpt-3.5-turbo` or even cheaper) to extract only the most relevant sentences/snippets from that external text based on the user's query. Feed *only these snippets* into the final analysis prompt.
    *   **Goal:** Reduce the token count (and cost) of the final analysis call and keep it focused.
    *   **Importance:** **MEDIUM (Cost/Performance).** Can significantly save tokens/cost if external data is verbose.

7.  **P7: Test Alternative Models (GPT-4o Mini):**
    *   **Task:** Now that the pipeline is more robust, swap the model used for the final analysis (Phase 3/P4) from `gpt-3.5-turbo` to `gpt-4o-mini`. Compare the quality, speed, and (if using your own key) cost of the generated analyses for several test queries. Consider also testing it for the initial query decomposition (Phase 1).
    *   **Goal:** Evaluate if the newer, potentially more capable model offers better results for a comparable cost.
    *   **Importance:** **MEDIUM (Quality Exploration).** Important evaluation step once the core system is working well.

8.  **P8: Implement Query Clarification:**
    *   **Task:** Add logic (likely in `/chat` and the initial LLM extraction) to detect ambiguous queries. If detected, have the backend respond by asking the user for clarification instead of proceeding with a poor search. Requires frontend changes to handle this state.
    *   **Goal:** Improve user experience and result relevance for vague queries.
    *   **Importance:** **MEDIUM (UX).** Good feature for a polished app, but less critical than fixing core search logic first.

9.  **P9: Consider Multi-Stage Filtering (Shallow Fetch):**
    *   **Task:** If P3 (LLM Re-ranking) still results in too many irrelevant candidates making it to the full deep dive (P4), consider adding an intermediate step. Fetch *basic* Place Details (types, price) for a larger set (e.g., Top 15) after ranking, apply simple filters, then select the final Top N for the *full* deep dive.
    *   **Goal:** Further optimize costs by filtering more candidates before expensive calls.
    *   **Importance:** **LOW (Optimization).** Only necessary if other steps aren't sufficient; adds complexity.

10. **P10: Explore Advanced Data Sources (OSM/Foursquare/etc.):**
    *   **Task:** Integrate data lookups from OSM, Foursquare, or other structured sources during candidate generation (Phase 1).
    *   **Goal:** Potentially find candidates or specific requirement tags missed by Google/Web/Reddit.
    *   **Importance:** **LOW (Project Scope).** Adds significant complexity (API management, ID mapping) for potentially marginal gains over a well-functioning Web/Reddit integration.

11. **P11: Enhance Map/UI Filtering:**
    *   **Task:** Add frontend controls to filter displayed results (map/list) based on criteria like rating, price, etc.
    *   **Goal:** Improve user interaction with the results.
    *   **Importance:** **LOW (Frontend Enhancement).** Primarily a UI feature, separate from backend search logic improvement.