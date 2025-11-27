print('Hello from dbt-common')
print('First change')
print('second change')
print('third change')
print('four change')
print('fifth change')
print('fifth change')
print('Hello from dbt-common')
print('First change')
print('second change')
print('third change')
print('four change')
print('fifth change')
print('fifth change')
print('fifth change')
print('fifth change')

#!/bin/bash
set -e # Exit on error
set -o pipefail # Fail on a pipe error

echo "Starting Certified Model Check..."

# 1. Define the certified tag string to look for.
#    This pattern allows for optional whitespace.
CERTIFIED_TAG_PATTERN="IS_CERTIFIED:[[:space:]]*\"TRUE\""

# 2. Get variables from workflow environment
base_ref="$BASE_REF"
domain_owners="$DOMAIN_OWNERS_LIST"

if [ -z "$base_ref" ]; then
  echo "::error:: BASE_REF environment variable is not set."
  exit 1
fi
if [ -z "$domain_owners" ]; then
  echo "::error:: DOMAIN_OWNERS_LIST environment variable is not set."
  exit 1
fi

# 3. Get list of all changed files compared to the target branch
echo "Fetching diff against origin/${base_ref}..."
git fetch origin "$base_ref" --depth=1
diff_files=$(git diff --name-only "origin/${base_ref}" HEAD)

if [ -z "$diff_files" ]; then
  echo "No files changed."
  echo "requires_review=false" >> "$GITHUB_OUTPUT"
  exit 0
fi

echo "Changed files:"
echo "$diff_files"

requires_review=false

# 4. Loop through each changed file
while IFS= read -r file; do
  
  # ---
  # Case 1: A model's .sql file was changed.
  # We must check its .yml config file(s).
  # ---
  if [[ "$file" == "dbt/models/"*".sql" ]]; then
    echo "Checking changed SQL model: $file"
    model_dir=$(dirname "$file")
    model_name=$(basename "$file" .sql)
    
    # Define directories to search for YML files:
    # 1. The model's own directory
    # 2. The parent directory (for a shared schema.yml)
    search_dirs=("$model_dir" "$(dirname "$model_dir")")
    
    # De-duplicate directories (in case model_dir is root)
    unique_search_dirs=($(printf "%s\n" "${search_dirs[@]}" | sort -u))

    for dir in "${unique_search_dirs[@]}"; do
      if [ -d "$dir" ]; then
        for yml_file in "$dir"/*.yml; do
          if [ -f "$yml_file" ]; then
            echo "  Checking corresponding config: $yml_file"
            
            # Use awk to find the model's specific block and check for the tag.
            # 1. Set Record Separator (RS) to "- name:" to split file by model definitions.
            # 2. Check if the current record (model block) starts with our model_name.
            # 3. If it is, check if *that block* contains the certified tag pattern.
            is_certified=$(awk -v model="$model_name" -v tag="$CERTIFIED_TAG_PATTERN" '
              BEGIN { RS = "\n[[:space:]]*- name:" }
              $0 ~ "^[[:space:]]*" model "[[:space:]]*(\n|$)" {
                if ($0 ~ tag) {
                  print "true"
                  exit
                }
              }
            ' "$yml_file")
            
            if [ "$is_certified" == "true" ]; then
               echo "  Found model '$model_name' with certified tag in '$yml_file'. Triggering review."
               requires_review=true
               break 2 # Break out of both yml_file and dir loops
            fi
          fi
        done
      fi
    done
  
  # ---
  # Case 2: A .yml config file was changed directly.
  # We check this file for the "certified" tag.
  # ---
  elif [[ "$file" == "dbt/models/"*".yml" ]]; then
    echo "Checking changed YML config: $file"
    # Check if the tag exists *anywhere* in the changed file
    if grep -q -E "$CERTIFIED_TAG_PATTERN" "$file"; then
      echo "  Found certified tag in changed YML. Triggering review."
      requires_review=true
    fi
  fi
  
  # If we've found a reason to review, we can stop checking
  if [ "$requires_review" = true ]; then
    break
  fi
  
done <<< "$diff_files" # Feed the diff_files into the loop

# 5. Output results for the workflow to use
echo "Review required: $requires_review"
echo "requires_review=$requires_review" >> "$GITHUB_OUTPUT"

if [ "$requires_review" = true ]; then
  echo "DOMAIN_OWNERS=$domain_owners" >> "$GITHUB_OUTPUT"
fi

echo "Certified Model Check complete."
exit 0





name: Certified Model Check

on:
  pull_request:
    types: [opened, synchronize, reopened]

# Add permissions for the job to add reviewers
permissions:
  pull-requests: write
  contents: read

jobs:
  check_certified_model:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          # Fetch all history so we can diff against the base branch
          fetch-depth: 0

      - name: Verify script existence
        run: |
          if [ ! -f .github/workflows/check_certified_model.sh ]; then
            echo "::error:: Script not found at .github/workflows/check_certified_model.sh"
            exit 1
          fi

      - name: Set script permissions
        run: chmod +x .github/workflows/check_certified_model.sh

      - name: Run Certified Model Check
        id: certified_check
        run: .github/workflows/check_certified_model.sh
        env:
          # Pass the *name* of the base branch (e.g., 'develop')
          BASE_REF: ${{ github.base_ref }}
          
          # -----------------------------------------------------------
          # **ACTION REQUIRED**: Update this list with GitHub usernames
          # -----------------------------------------------------------
          DOMAIN_OWNERS_LIST: "github_user_1,github_user_2"

      - name: Fail and Add Reviewers if Certified Model Check requires review
        if: steps.certified_check.outputs.requires_review == 'true'
        run: |
          echo "::error:: This PR modifies a certified model and requires mandatory approval from ${{ steps.certified_check.outputs.DOMAIN_OWNERS }}."
          
          # Use GitHub CLI to add reviewers
          gh pr edit ${{ github.event.pull_request.number }} --add-reviewer "${{ steps.certified_check.outputs.DOMAIN_OWNERS }}"
          
          exit 1 # Fail the job to block the PR
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}





name: Certified Model Check

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write # To add reviewers
  contents: read       # To check out code

jobs:
  check_certified_model:
    runs-on: ubuntu-latest
    
    # Pass the result to the next job
    outputs:
      requires_review: ${{ steps.certified_check.outputs.requires_review }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Verify script existence
        run: |
          if [ ! -f .github/workflows/check_certified_model.sh ]; then
            echo "::error:: Script not found at .github/workflows/check_certified_model.sh"
            exit 1
          fi

      - name: Set script permissions
        run: chmod +x .github/workflows/check_certified_model.sh

      - name: Run Certified Model Check
        id: certified_check
        run: .github/workflows/check_certified_model.sh
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pull_request.head.sha }}
          # Update this list with GitHub usernames for the comment/assign step
          DOMAIN_OWNERS_LIST: "github_user_1,github_user_2"
          
      - name: Add Reviewers (Notification)
        # If review is required, we add them as reviewers, but we DO NOT fail the job here.
        if: steps.certified_check.outputs.requires_review == 'true'
        run: |
          echo "Certified model modified. Adding Domain Owners as reviewers."
          gh pr edit ${{ github.event.pull_request.number }} --add-reviewer "${{ env.DOMAIN_OWNERS_LIST }}"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  # ----------------------------------------------------
  # NEW JOB: This is the "Gate"
  # ----------------------------------------------------
  wait_for_approval:
    runs-on: ubuntu-latest
    needs: [check_certified_model]
    # Only run this job if the script found a certified model change
    if: needs.check_certified_model.outputs.requires_review == 'true'
    
    # This matches the Environment you created in Settings
    environment: Certified Model Review
    
    steps:
      - name: Waiting for approval
        run: |
          echo "This job is paused."
          echo "It is waiting for a Domain Owner to approve the deployment in the 'Certified Model Review' environment."
          echo "Once approved, this check will turn green and the PR can merge."





          name: Certified Model Check

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  pull-requests: write # Still needed to add reviewers
  contents: read

jobs:
  check_certified_model:
    runs-on: ubuntu-latest
    
    # ----------------------------------------------------
    # STEP 1: Add an 'outputs' section
    # ----------------------------------------------------
    outputs:
      requires_review: ${{ steps.certified_check.outputs.requires_review }}

    steps:
      - name: Checkout code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Verify script existence
        run: |
          if [ ! -f .github/workflows/check_certified_model.sh ]; then
            echo "::error:: Script not found at .github/workflows/check_certified_model.sh"
            exit 1
          fi

      - name: Set script permissions
        run: chmod +x .github/workflows/check_certified_model.sh

      - name: Run Certified Model Check
        id: certified_check
        run: .github/workflows/check_certified_model.sh
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
          HEAD_SHA: ${{ github.event.pullrequest.head.sha }}
          # ACTION REQUIRED: Update this list with GitHub usernames
          DOMAIN_OWNERS_LIST: "github_user_1,github_user_2"
          
      # ----------------------------------------------------
      # STEP 2: Add reviewers, but DO NOT fail the job
      # ----------------------------------------------------
      - name: Add Reviewers if Certified Model Check requires review
        if: steps.certified_check.outputs.requires_review == 'true'
        run: |
          echo "Certified model modified. Adding Domain Owners as reviewers."
          gh pr edit ${{ github.event.pull_request.number }} --add-reviewer "${{ env.DOMAIN_OWNERS_LIST }}"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  # ----------------------------------------------------
  # STEP 3: Add this NEW job
  # ----------------------------------------------------
  wait_for_approval:
    runs-on: ubuntu-latest
    # This job depends on the first one
    needs: [check_certified_model]
    # This job ONLY runs if the script output was 'true'
    if: needs.check_certified_model.outputs.requires_review == 'true'
    
    # This is the magic part!
    # It uses the Environment you created.
    environment: Certified Model Review
    
    steps:
      - name: Waiting for approval from Domain Owners
        run: |
          echo "This job will 'pause' until a required reviewer from the 'Certified Model Review' environment approves it."
          echo "The PR will be blocked from merging until this approval is given."






#!/bin/bash
set -e # Exit on error
set -o pipefail # Fail on a pipe error

echo "Starting Certified Model Check..."

# 1. Define the certified tag string to look for
# UPDATE: This regex now matches both "TRUE" and 'TRUE'
CERTIFIED_TAG_PATTERN="IS_CERTIFIED:[[:space:]]*['\"]TRUE['\"]"

# 2. Get variables from workflow environment
base_sha="$BASE_SHA"
head_sha="$HEAD_SHA"
domain_owners="$DOMAIN_OWNERS_LIST"

# Check that variables are set
if [ -z "$base_sha" ]; then
  echo "::error:: BASE_SHA environment variable is not set."
  exit 1
fi
if [ -z "$head_sha" ]; then
  echo "::error:: HEAD_SHA environment variable is not set."
  exit 1
fi
if [ -z "$domain_owners" ]; then
  echo "::error:: DOMAIN_OWNERS_LIST environment variable is not set."
  exit 1
fi

# 3. Get list of all changed files using the exact SHAs
echo "Finding diff between base (${base_sha}) and head (${head_sha})"

# Find the common ancestor (merge-base) of the two commits
merge_base=$(git merge-base "$base_sha" "$head_sha")
echo "Calculated merge-base: $merge_base"

# Diff from the merge-base to the HEAD of the PR
diff_files=$(git diff --name-only "$merge_base" "$head_sha")

if [ -z "$diff_files" ]; then
  echo "No files changed."
  echo "requires_review=false" >> "$GITHUB_OUTPUT"
  exit 0
fi

echo "Changed files:"
echo "$diff_files"

requires_review=false

# 4. Loop through each changed file
while IFS= read -r file; do
  
  # ---
  # Case 1: A model's .sql file was changed.
  # ---
  if [[ "$file" == "dbt/models/"*".sql" ]]; then
    echo "Checking changed SQL model: $file"
    model_dir=$(dirname "$file")
    model_name=$(basename "$file" .sql)
    
    # Define directories to search for YML files
    search_dirs=("$model_dir" "$(dirname "$model_dir")")
    unique_search_dirs=($(printf "%s\n" "${search_dirs[@]}" | sort -u))

    for dir in "${unique_search_dirs[@]}"; do
      if [ -d "$dir" ]; then
        for yml_file in "$dir"/*.yml; do
          if [ -f "$yml_file" ]; then
            echo "  Checking corresponding config: $yml_file"
            
            # Use awk to find the model's specific block and check for the tag
            is_certified=$(awk -v model="$model_name" -v tag="$CERTIFIED_TAG_PATTERN" '
              BEGIN { RS = "\n[[:space:]]*- name:" }
              $0 ~ "^[[:space:]]*" model "[[:space:]]*(\n|$)" {
                if ($0 ~ tag) {
                  print "true"
                  exit
                }
              }
            ' "$yml_file")
            
            if [ "$is_certified" == "true" ]; then
               echo "  Found model '$model_name' with certified tag in '$yml_file'. Triggering review."
               requires_review=true
               break 2 # Break out of both yml_file and dir loops
            fi
          fi
        done
      fi
    done
  
  # ---
  # Case 2: A .yml config file was changed directly.
  # ---
  elif [[ "$file" == "dbt/models/"*".yml" ]]; then
    echo "Checking changed YML config: $file"
    # Check if the tag exists *anywhere* in the changed file
    if grep -q -E "$CERTIFIED_TAG_PATTERN" "$file"; then
      echo "  Found certified tag in changed YML. Triggering review."
      requires_review=true
    fi
  fi
  
  # If we've found a reason to review, we can stop checking
  if [ "$requires_review" = true ]; then
    break
  fi
  
done <<< "$diff_files" # Feed the diff_files into the loop

# 5. Output results for the workflow to use
echo "Review required: $requires_review"
echo "requires_review=$requires_review" >> "$GITHUB_OUTPUT"

if [ "$requires_review" = true ]; then
  echo "DOMAIN_OWNERS=$domain_owners" >> "$GITHUB_OUTPUT"
fi

echo "Certified Model Check complete."
exit 0




#!/bin/bash
set -e # Exit on error
set -o pipefail # Fail on a pipe error

echo "Starting Certified Model Check..."

# 1. Define the certified tag string to look for.
CERTIFIED_TAG_PATTERN="IS_CERTIFIED:[[:space:]]*['\"]TRUE['\"]"

# 2. Get variables from workflow environment
base_sha="$BASE_SHA"
head_sha="$HEAD_SHA"

if [ -z "$base_sha" ]; then
  echo "::error:: BASE_SHA environment variable is not set."
  exit 1
fi
if [ -z "$head_sha" ]; then
  echo "::error:: HEAD_SHA environment variable is not set."
  exit 1
fi

# 3. Get list of all changed files using the exact SHAs
echo "Finding diff between base (${base_sha}) and head (${head_sha})"
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

# 4. Loop through each changed file
while IFS= read -r file; do
  
  # -------------------------------------------------------------------------
  # CHECK A: Validate that IS_CERTIFIED is ONLY used in 'consumption' folder
  # -------------------------------------------------------------------------
  if [[ "$file" == "dbt/"* ]]; then
    # Check if file has the certified tag
    if grep -q -E "$CERTIFIED_TAG_PATTERN" "$file"; then
      
      # If tag is found, check if the file path is INSIDE 'dbt/models/consumption'
      if [[ "$file" != "dbt/models/consumption/"* ]]; then
        echo "::error:: ❌ ILLEGAL TAG DETECTED!"
        echo "::error:: The tag 'IS_CERTIFIED: TRUE' was found in '$file'."
        echo "::error:: This tag is ONLY allowed in the 'dbt/models/consumption/' directory."
        exit 1 # Fail the workflow immediately
      fi
    fi
  fi

  # -------------------------------------------------------------------------
  # CHECK B: Normal Logic - Detect changes to certified models in Consumption
  # -------------------------------------------------------------------------
  
  # Only process files inside dbt/models/consumption for the review trigger
  if [[ "$file" == "dbt/models/consumption/"* ]]; then

    # Case 1: A .sql file changed
    if [[ "$file" == *".sql" ]]; then
      echo "Checking changed SQL model: $file"
      model_dir=$(dirname "$file")
      model_name=$(basename "$file" .sql)
      
      search_dirs=("$model_dir" "$(dirname "$model_dir")")
      unique_search_dirs=($(printf "%s\n" "${search_dirs[@]}" | sort -u))

      for dir in "${unique_search_dirs[@]}"; do
        if [ -d "$dir" ]; then
          for yml_file in "$dir"/*.yml; do
            if [ -f "$yml_file" ]; then
              echo "  Checking corresponding config: $yml_file"
              
              is_certified=$(awk -v model="$model_name" -v tag="$CERTIFIED_TAG_PATTERN" '
                BEGIN { RS = "\n[[:space:]]*- name:" }
                $0 ~ "^[[:space:]]*" model "[[:space:]]*(\n|$)" {
                  if ($0 ~ tag) { print "true"; exit }
                }
              ' "$yml_file")
              
              if [ "$is_certified" == "true" ]; then
                 echo "  Found certified model '$model_name' changed. Triggering review."
                 requires_review=true
                 break 2
              fi
            fi
          done
        fi
      done
    
    # Case 2: A .yml file changed directly
    elif [[ "$file" == *".yml" ]]; then
      echo "Checking changed YML config: $file"
      if grep -q -E "$CERTIFIED_TAG_PATTERN" "$file"; then
        echo "  Found certified tag in changed YML. Triggering review."
        requires_review=true
      fi
    fi
  fi
  
  if [ "$requires_review" = true ]; then
    break
  fi
  
done <<< "$diff_files"

# 5. Output results
echo "Review required: $requires_review"
echo "requires_review=$requires_review" >> "$GITHUB_OUTPUT"

echo "Certified Model Check complete."
exit 0






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

# Trackers for the folder separation rule
has_consumption_changes=false
has_curated_changes=false
requires_review=false

# Loop through files
while IFS= read -r file; do
  
  # --- 1. TRACK FOLDER CHANGES (For Separation Rule) ---
  if [[ "$file" == "dbt/models/consumption/"* ]]; then
    has_consumption_changes=true
  elif [[ "$file" == "dbt/models/curated/"* ]]; then
    has_curated_changes=true
  fi

  # --- 2. SECURITY CHECK (The "Red Light") ---
  # If tag exists but NOT in consumption -> FAIL
  if [[ "$file" == "dbt/"* ]] && grep -q -E "$CERTIFIED_TAG_PATTERN" "$file"; then
     if [[ "$file" != "dbt/models/consumption/"* ]]; then
        echo "::error:: ❌ ILLEGAL TAG: 'IS_CERTIFIED' found in '$file'."
        echo "::error:: This tag is ONLY allowed in 'dbt/models/consumption/'."
        exit 1
     fi
  fi

  # --- 3. CERTIFIED CHECK (The "Green Light") ---
  # Check if we need a review
  if [[ "$file" == "dbt/models/consumption/"* ]]; then
    
    # Check SQL files
    if [[ "$file" == *".sql" ]]; then
      model_dir=$(dirname "$file")
      model_name=$(basename "$file" .sql)
      
      search_dirs=("$model_dir" "$(dirname "$model_dir")")
      for dir in "${search_dirs[@]}"; do
        if [ -d "$dir" ]; then
          for yml_file in "$dir"/*.yml; do
            if [ -f "$yml_file" ]; then
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

done <<< "$diff_files"

# --- 4. FINAL VALIDATION: SEPARATION OF CONCERNS ---
# If both folders were touched, FAIL the workflow.
if [ "$has_consumption_changes" = true ] && [ "$has_curated_changes" = true ]; then
  echo "::error:: ❌ MULTI-LAYER CHANGE DETECTED!"
  echo "::error:: This PR modifies files in BOTH 'dbt/models/consumption' and 'dbt/models/curated'."
  echo "::error:: Best Practice: Please separate these changes into two different Pull Requests."
  exit 1
fi

echo "requires_review=$requires_review" >> "$GITHUB_OUTPUT"
