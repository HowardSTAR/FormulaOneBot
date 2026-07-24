#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
assets_dir="$project_dir/app/assets"
archive_path="$project_dir/app-assets.zip"
temporary_archive="$project_dir/.app-assets.tmp.zip"

if [ ! -d "$assets_dir" ]; then
    echo "Каталог app/assets не найден. Сначала распакуйте app-assets.zip."
    exit 1
fi

rm -f "$temporary_archive"
(
    cd "$project_dir"
    zip -q -r "$temporary_archive" app/assets \
        -x '*/.DS_Store' '*/__MACOSX/*'
)
mv "$temporary_archive" "$archive_path"

echo "Создан архив: $archive_path"
