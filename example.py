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
