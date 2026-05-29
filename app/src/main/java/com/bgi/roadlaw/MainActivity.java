package com.bgi.roadlaw;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.view.KeyEvent;

import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

/**
 * MainActivity — Loads the Roadlaw web UI from assets/ into a full-screen WebView.
 * Includes file chooser support for PDF upload via <input type="file">.
 */
public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private ValueCallback<Uri[]> fileChooserCallback;

    // Modern ActivityResult launcher for file picker
    private final ActivityResultLauncher<Intent> filePickerLauncher =
            registerForActivityResult(
                    new ActivityResultContracts.StartActivityForResult(),
                    result -> {
                        if (fileChooserCallback == null) return;

                        Uri[] results = null;
                        if (result.getResultCode() == Activity.RESULT_OK && result.getData() != null) {
                            String dataString = result.getData().getDataString();
                            if (dataString != null) {
                                results = new Uri[]{Uri.parse(dataString)};
                            }
                        }
                        fileChooserCallback.onReceiveValue(results);
                        fileChooserCallback = null;
                    }
            );

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Handle system bar insets for edge-to-edge display
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.main), (v, insets) -> {
            Insets systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars());
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom);
            return insets;
        });

        // ── Setup WebView ──
        webView = findViewById(R.id.webview);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);

        // Keep navigation inside the WebView
        webView.setWebViewClient(new WebViewClient());

        // Register AndroidBridge
        webView.addJavascriptInterface(new WebAppInterface(this), "AndroidBridge");

        // ── WebChromeClient with File Chooser support ──
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(
                    WebView webView,
                    ValueCallback<Uri[]> callback,
                    FileChooserParams fileChooserParams) {

                // Cancel any existing callback
                if (fileChooserCallback != null) {
                    fileChooserCallback.onReceiveValue(null);
                }
                fileChooserCallback = callback;

                // Launch file picker intent
                Intent intent = fileChooserParams.createIntent();
                try {
                    filePickerLauncher.launch(intent);
                } catch (Exception e) {
                    fileChooserCallback = null;
                    return false;
                }
                return true;
            }
        });

        // Load the app from assets
        webView.loadUrl("file:///android_asset/index.html");
    }

    /**
     * Handle back button — go back in WebView history if possible.
     */
    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && webView.canGoBack()) {
            webView.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    // ═══════════════════════════════════════════════════════════
    //  ANDROID BRIDGE (Offline Sync & JSON Parsing)
    // ═══════════════════════════════════════════════════════════
    public class WebAppInterface {
        Context mContext;
        private final String FILE_NAME = "challans_offline.json";
        private final String JSON_URL = "https://uzvywflybfafameoqwhp.supabase.co/storage/v1/object/public/app-data/challans.json";

        WebAppInterface(Context c) {
            mContext = c;
        }

        @android.webkit.JavascriptInterface
        public void downloadOfflineData() {
            java.util.concurrent.Executors.newSingleThreadExecutor().execute(() -> {
                try {
                    java.net.URL url = new java.net.URL(JSON_URL);
                    java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("GET");
                    java.io.InputStream is = conn.getInputStream();
                    java.io.FileOutputStream fos = mContext.openFileOutput(FILE_NAME, Context.MODE_PRIVATE);
                    byte[] buffer = new byte[4096];
                    int len;
                    while ((len = is.read(buffer)) != -1) {
                        fos.write(buffer, 0, len);
                    }
                    fos.close();
                    is.close();
                } catch (Exception e) {
                    e.printStackTrace();
                }
            });
        }

        @android.webkit.JavascriptInterface
        public boolean isOfflineModeEnabled() {
            java.io.File file = new java.io.File(mContext.getFilesDir(), FILE_NAME);
            return file.exists();
        }

        @android.webkit.JavascriptInterface
        public void deleteOfflineData() {
            java.io.File file = new java.io.File(mContext.getFilesDir(), FILE_NAME);
            if (file.exists()) {
                file.delete();
            }
        }

        @android.webkit.JavascriptInterface
        public long getLastSyncTime() {
            java.io.File file = new java.io.File(mContext.getFilesDir(), FILE_NAME);
            return file.exists() ? file.lastModified() : 0;
        }

        @android.webkit.JavascriptInterface
        public String getDbCount() {
            try {
                String jsonStr = readOfflineFile();
                if (jsonStr == null) return "0";
                org.json.JSONArray arr = new org.json.JSONArray(jsonStr);
                return String.valueOf(arr.length());
            } catch (Exception e) {
                return "0";
            }
        }

        @android.webkit.JavascriptInterface
        public String searchChallanOffline(String query, String state, String vehicle) {
            try {
                String jsonStr = readOfflineFile();
                if (jsonStr == null) {
                    return "{\"found\":false,\"message\":\"Offline data missing\"}";
                }

                org.json.JSONArray allRecords = new org.json.JSONArray(jsonStr);
                String searchQ = query.toLowerCase().trim();
                String targetState = state != null ? state.toLowerCase().trim() : "all";

                org.json.JSONArray stateResults = new org.json.JSONArray();
                org.json.JSONArray nationalResults = new org.json.JSONArray();
                int totalFine = 0;

                for (int i = 0; i < allRecords.length(); i++) {
                    org.json.JSONObject record = allRecords.getJSONObject(i);
                    String recState = record.optString("state_name", "").toLowerCase();
                    org.json.JSONArray keywords = record.optJSONArray("keywords");

                    boolean keywordMatch = false;
                    String matchedKw = "";
                    if (keywords != null) {
                        for (int j = 0; j < keywords.length(); j++) {
                            String kw = keywords.optString(j).toLowerCase();
                            if (searchQ.contains(kw) || kw.contains(searchQ)) {
                                keywordMatch = true;
                                matchedKw = kw;
                                break;
                            }
                        }
                    }

                    if (keywordMatch) {
                        record.put("matched_keyword", matchedKw);
                        if (recState.equals(targetState)) {
                            record.put("source_jurisdiction", record.optString("state_name"));
                            record.put("priority", "STATE");
                            stateResults.put(record);
                            totalFine += record.optInt("fine_amount", 0);
                        } else if (recState.equals("national") || recState.equals("all")) {
                            record.put("source_jurisdiction", "National");
                            record.put("priority", "NATIONAL");
                            nationalResults.put(record);
                            if (stateResults.length() == 0) {
                                totalFine += record.optInt("fine_amount", 0);
                            }
                        }
                    }
                }

                org.json.JSONArray finalResults = new org.json.JSONArray();
                for (int i = 0; i < stateResults.length(); i++) finalResults.put(stateResults.get(i));
                for (int i = 0; i < nationalResults.length(); i++) {
                    if (stateResults.length() == 0) {
                        finalResults.put(nationalResults.get(i));
                    }
                }

                org.json.JSONObject response = new org.json.JSONObject();
                response.put("found", finalResults.length() > 0);
                response.put("results", finalResults);
                response.put("national_comparison", new org.json.JSONArray());
                response.put("total_fine", totalFine);
                response.put("currency", "INR");
                return response.toString();

            } catch (Exception e) {
                return "{\"found\":false,\"error\":\"" + e.getMessage() + "\"}";
            }
        }

        private String readOfflineFile() {
            try {
                java.io.File file = new java.io.File(mContext.getFilesDir(), FILE_NAME);
                if (!file.exists()) return null;
                java.io.BufferedReader br = new java.io.BufferedReader(new java.io.FileReader(file));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = br.readLine()) != null) sb.append(line);
                br.close();
                return sb.toString();
            } catch (Exception e) {
                return null;
            }
        }
    }
}