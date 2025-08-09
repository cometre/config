#!/bin/sh

/bin/rm -fv *.list
cp -fv out/*.list .

if [ -z "$(git status --porcelain)" ]; then
  echo "No changes to commit."
  exit 0
fi

now=$(date +%Y%m%d%H%M)

delete_first_line() {
    local file="$1"

    if sed --version >/dev/null 2>&1; then
        # GNU sed (Linux)
        sed -i "1d" "$file"
    else
        # BSD sed (macOS)
        sed -i '' "1d" "$file"
    fi
}

update_timestamp() {
    local file="$1"
    if sed --version >/dev/null 2>&1; then
        # GNU sed (Linux)
        sed -i "1i# UPDATED:$now" "$file"
    else
        # BSD sed (macOS)
        sed -i '' "1i\\
# UPDATED:$now
" "$file"
    fi
}

delete_first_line sr_direct_ru_geo_and_asn.conf
update_timestamp sr_direct_ru_geo_and_asn.conf
delete_first_line sr_reject_ru_geo_and_asn.conf
update_timestamp sr_reject_ru_geo_and_asn.conf

git add *.list
git add *.conf
git commit -m "update lists [$now]"
git push origin master
if [ $? -ne 0 ]; then
  echo "Failed to push changes to remote repository."
  exit 1
fi

echo "Changes pushed successfully."
