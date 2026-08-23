#!/bin/sh
set -eu

package_id=com.devolverdigital.ballxpit
save_root=/sdcard/Android/data/$package_id/files
device_id=${1:-}
destination=${2:-backups}

if [ -z "$device_id" ]; then
  echo "usage: $0 DEVICE_SERIAL [DESTINATION]" >&2
  exit 2
fi

device_state=$(adb -s "$device_id" get-state 2>/dev/null || true)
if [ "$device_state" != device ]; then
  echo "error: ADB device $device_id is not authorized and online" >&2
  exit 1
fi

model=$(adb -s "$device_id" shell getprop ro.product.model | tr -d '\r')
version=$(adb -s "$device_id" shell dumpsys package "$package_id" |
  sed -n 's/^[[:space:]]*versionName=//p' | head -1 | tr -d '\r')
if [ -z "$version" ]; then
  echo "error: $package_id is not installed for the active Android user" >&2
  exit 1
fi
if adb -s "$device_id" shell pidof "$package_id" | grep -q '[0-9]'; then
  echo "error: close $package_id before taking a consistent snapshot" >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_dir=$destination/$model-$device_id-$timestamp-v$version
snapshot_dir=$final_dir.partial
mkdir -p "$destination"
if [ -e "$final_dir" ] || [ -e "$snapshot_dir" ]; then
  echo "error: snapshot path already exists: $final_dir" >&2
  exit 1
fi
mkdir "$snapshot_dir"

files="meta1.yankai meta1_backup.yankai saveslotinfo.balls"
if adb -s "$device_id" shell test -f "$save_root/stats.csv"; then
  files="$files stats.csv"
fi

device_manifest() {
  for filename in $files; do
    adb -s "$device_id" shell sha256sum "$save_root/$filename"
  done | sed 's#  .*/#  #'
}

device_manifest > "$snapshot_dir/device-sha256-before.txt"
for filename in $files; do
  adb -s "$device_id" pull "$save_root/$filename" "$snapshot_dir/$filename"
done
device_manifest > "$snapshot_dir/device-sha256-after.txt"
diff -u "$snapshot_dir/device-sha256-before.txt" "$snapshot_dir/device-sha256-after.txt"
(cd "$snapshot_dir" && shasum -a 256 -c device-sha256-after.txt >&2)
chmod a-w "$snapshot_dir"/* "$snapshot_dir"
mv "$snapshot_dir" "$final_dir"

echo "$final_dir"
