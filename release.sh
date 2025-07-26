#!/bin/sh

/bin/rm -fv *.list
cp -fv out/*.list .

if [ -z "$(git status --porcelain)" ]; then
  echo "No changes to commit."
  exit 0
fi

now=$(date +%Y%m%d%H%M)

git add *.list
git commit -m "update lists [$now]"
git push origin master
if [ $? -ne 0 ]; then
  echo "Failed to push changes to remote repository."
  exit 1
fi

sed -i '' "1d" sr_direct_ru_geo_and_asn.conf
sed -i '' "1i\\
# UPDATED:$now
" sr_direct_ru_geo_and_asn.conf

sed -i '' "1d" sr_reject_ru_geo_and_asn.conf
sed -i '' "1i\\
# UPDATED:$now
" sr_reject_ru_geo_and_asn.conf

echo "Changes pushed successfully."
