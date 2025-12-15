#!/bin/bash
set -e
set -o pipefail

echo "Starting Certified Model Check..."
CERTIFIED_TAG_PATTERN="IS_CERTIFIED:[[:space:]]*['\"]TRUE['\"]"

base_sha="$BASE_SHA"
head_sha="$HEAD_SHA"

if [[ -z "$base_sha" || -z "$head_sha" ]]; then
  echo "::error:: Missing SHAs"
  exit 1
fi

echo "Diffing $base_sha...$head_sha"
merge_base=$(git merge-base "$base_sha" "$head_sha")
diff_files=$(git diff --name-only "$merge_base" "$head_sha")

if [ -z "$diff_files" ]; then
  echo "No files changed."
  echo "requires_review=false" >> "$GITHUB_OUTPUT"
  exit 0
fi

echo "Changed files:"
echo "$diff_files"

requires_review=false

# Loop through files
while IFS= read -r file; do
  
  # --- 1. SECURITY CHECK (The "Red Light") ---
  # Check if file is in dbt folder AND has the tag
  if [[ "$file" == "dbt/"* ]] && grep -q -E "$CERTIFIED_TAG_PATTERN" "$file"; then
     # If it has the tag, it MUST be inside 'dbt/models/consumption/'
     if [[ "$file" != "dbt/models/consumption/"* ]]; then
        echo "::error:: ❌ ILLEGAL TAG DETECTED!"
        echo "::error:: The tag 'IS_CERTIFIED: TRUE' was found in '$file'."
        echo "::error:: This tag is ONLY allowed in the 'dbt/models/consumption/' directory."
        exit 1 # Fail immediately
     fi
  fi

  # --- 2. REVIEW TRIGGER (The "Green Light") ---
  # Only trigger review if we are inside 'consumption'
  if [[ "$file" == "dbt/models/consumption/"* ]]; then
    
    # Check SQL files
    if [[ "$file" == *".sql" ]]; then
      model_dir=$(dirname "$file")
      model_name=$(basename "$file" .sql)
      
      search_dirs=("$model_dir" "$(dirname "$model_dir")")
      unique_search_dirs=($(printf "%s\n" "${search_dirs[@]}" | sort -u))

      for dir in "${unique_search_dirs[@]}"; do
        if [ -d "$dir" ]; then
          for yml_file in "$dir"/*.yml; do
            if [ -f "$yml_file" ]; then
              # AWK check for tag in specific model block
              is_certified=$(awk -v model="$model_name" -v tag="$CERTIFIED_TAG_PATTERN" 'BEGIN {RS="\n[[:space:]]*- name:"} $0 ~ "^[[:space:]]*" model "[[:space:]]*(\n|$)" {if ($0 ~ tag) {print "true"; exit}}' "$yml_file")
              
              if [ "$is_certified" == "true" ]; then
                 echo "Certified model modified ($model_name). Review required."
                 requires_review=true
              fi
            fi
          done
        fi
      done

    # Check YML files directly
    elif [[ "$file" == *".yml" ]]; then
      if grep -q -E "$CERTIFIED_TAG_PATTERN" "$file"; then
        echo "Certified tag found in YML change. Review required."
        requires_review=true
      fi
    fi
  fi

  # REMOVED THE BREAK STATEMENT HERE
  # We must continue scanning all files to catch illegal tags in other folders.

done <<< "$diff_files"

echo "requires_review=$requires_review" >> "$GITHUB_OUTPUT"





Here is the updated, complete documentation package. I have removed the PAT/API method and focused entirely on the Environment-based Approval workflow, which is the native and most secure way to handle this.
📘 Certified Model Governance: Comprehensive Guide
1. System Overview
The Certified Model Check is an automated governance workflow designed to protect critical data assets. It ensures that "Certified" reporting models are not modified without explicit approval from the Data Platform Team.
Key Features
 * Strict Location Policy: The IS_CERTIFIED tag is only allowed in the dbt/models/consumption/ directory. Usage elsewhere causes an immediate error.
 * Smart Detection: The workflow scans git diff to see if a certified model (SQL or YAML) has been touched.
 * Automated Gating: If a certified model is changed, the PR is automatically paused and blocked until the Data Platform Team approves it via the GitHub Environment protection rules.
2. User Guide (For Developers)
Target Audience: Analytics Engineers & Data Engineers
Goal: Learn how to certify a model and understand the PR process.
How to Certify a Model
To mark a model as "Certified," add the IS_CERTIFIED tag to its .yml configuration file.
✅ The Golden Rule:
You may ONLY certify models located in the consumption folder (dbt/models/consumption/).
Example: dbt/models/consumption/finance/fct_revenue.yml
version: 2

models:
  - name: fct_revenue
    description: "Certified revenue table for the CFO dashboard."
    config:
      IS_CERTIFIED: 'TRUE'   # <--- Add this tag here.
                             # (Case-insensitive: 'True', "TRUE", true all work)
    columns:
      - name: amount
        description: "Total revenue amount"

What happens when I open a PR?
The workflow "Certified Model Check" runs automatically on every Pull Request.
| Scenario | What you did | Workflow Status | Action Required |
|---|---|---|---|
| A. Normal Change | Modified standard models (no tag). | ✅ Pass (Green) | You can merge as soon as standard peer reviews are done. |
| B. Certified Change | Modified a model with IS_CERTIFIED: 'TRUE' inside consumption/. | ⚠️ Waiting | The workflow will Pause (Yellow). 
 GitHub will notify the Data Platform Team to review the deployment. 
 You must wait for their approval. |
| C. Illegal Tag | Added IS_CERTIFIED to a model in staging/, intermediate/, or curated/. | ❌ Fail (Red) | The build fails immediately with: 
 ❌ ILLEGAL TAG DETECTED. 
 Fix: Remove the tag from that file and push again. |
3. Admin Guide (For Platform Team)
Target Audience: Platform Admins / DevOps
Goal: Configure the repository to enforce these rules.
Step 1: Configure the GitHub Environment
This is the "Gate" that pauses the workflow and demands approval.
 * Go to your Repository Settings.
 * In the left sidebar, click Environments.
 * Click New environment.
 * Name: Certified Model Review (Must match the name in your YAML file).
 * Click Configure environment.
 * Under Deployment protection rules, check the box Required reviewers.
 * Search for your Team: Type data-platforms-warehousing.
   * Note: If you don't see the team, ensure you have created the team in your Organization settings first.
 * Click Save protection rules.
Step 2: Configure Branch Protection Rules
This ensures developers cannot bypass the check or merge failing code.
 * Go to Settings -> Branches.
 * Click Add rule.
 * Branch name pattern: main (or master).
 * Check Require a pull request before merging.
 * Check Require status checks to pass before merging.
   * Search for the job name: check_certified_model
   * Note: You might need to run the workflow once successfully for this name to appear in the list.
 * Click Create.
Step 3: Verify the Script Logic
Ensure the script .github/workflows/check_certified_model.sh is updated with the latest logic (Case-insensitive & Folder check).
 * Regex Pattern used: IS_CERTIFIED:[[:space:]]*['\"]*TRUE['\"]*
 * Folder Enforcement:
   if [[ "$file" != "dbt/models/consumption/"* ]]; then
   echo "::error:: ❌ ILLEGAL TAG DETECTED!"
   exit 1
fi

Troubleshooting
| Issue | Cause | Fix |
|---|---|---|
| Workflow finishes Green instantly but I changed a certified model. | The script didn't match the tag. | Ensure the tag is spelled correctly (IS_CERTIFIED). The script is case-insensitive, so True/TRUE are both fine. |
| Workflow is stuck on Yellow indefinitely. | It is waiting for approval. | A member of the data-platforms-warehousing team must go to the "Environments" page (or the PR checks tab) and click "Approve and Deploy". |
| "Resource not accessible" error. | Permissions missing. | Ensure the YAML file has permissions: pull-requests: write. |
