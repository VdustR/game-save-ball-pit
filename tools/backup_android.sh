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
snapshot_dir=$destination/$model-$device_id-$timestamp-v$version
mkdir -p "$snapshot_dir"

adb -s "$device_id" shell sha256sum \
  "$save_root/meta1.yankai" \
  "$save_root/meta1_backup.yankai" \
  "$save_root/saveslotinfo.balls" \
  "$save_root/stats.csv" | sed 's#  .*/#  #' > "$snapshot_dir/device-sha256-before.txt"
for filename in meta1.yankai meta1_backup.yankai saveslotinfo.balls stats.csv; do
  adb -s "$device_id" pull "$save_root/$filename" "$snapshot_dir/$filename"
done
adb -s "$device_id" shell sha256sum \
  "$save_root/meta1.yankai" \
  "$save_root/meta1_backup.yankai" \
  "$save_root/saveslotinfo.balls" \
  "$save_root/stats.csv" | sed 's#  .*/#  #' > "$snapshot_dir/device-sha256-after.txt"
diff -u "$snapshot_dir/device-sha256-before.txt" "$snapshot_dir/device-sha256-after.txt"
(cd "$snapshot_dir" && shasum -a 256 -c device-sha256-after.txt)
chmod a-w "$snapshot_dir"/* "$snapshot_dir"

echo "$snapshot_dir"
