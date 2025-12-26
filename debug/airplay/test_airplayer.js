#!/usr/bin/env node

/**
 * Quick test of airplayer Node.js library for Samsung TV AirPlay compatibility
 * Run with: node test_airplayer.js
 */

const airplayer = require("airplayer");

console.log("🎬 Testing airplayer (Node.js AirPlay client)...");
console.log(
  "   Note: This will likely show the same Samsung TV compatibility issues as pyatv\n"
);

// Create airplayer instance (returns a list/emitter)
const list = airplayer();

// Listen for device discovery
list.on("update", (player) => {
  console.log(`✅ Found AirPlay device: ${player.name}`);

  // Check if this is our Samsung TV
  if (player.name && player.name.includes("Samsung")) {
    console.log(`🎯 Found Samsung TV! Testing streaming...`);

    // Test with a known working video
    const testUrl =
      "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4";

    player.play(testUrl, (err) => {
      if (err) {
        console.log(`❌ airplayer streaming failed: ${err.message}`);
        console.log("   This suggests airplayer has similar issues as pyatv");
      } else {
        console.log(`✅ airplayer streaming initiated successfully!`);
        console.log("   Check your TV to see if content is playing");
      }
    });
  }
});

// Start discovery
console.log("🔍 Scanning for AirPlay devices...");
console.log("   (This will run for 15 seconds)\n");

// Stop after 15 seconds
setTimeout(() => {
  console.log("\n⏰ Stopping discovery...");
  list.destroy();
  process.exit(0);
}, 10000);
