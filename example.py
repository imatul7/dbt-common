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

