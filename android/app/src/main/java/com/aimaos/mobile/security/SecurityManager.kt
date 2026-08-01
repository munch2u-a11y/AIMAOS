package com.aimaos.mobile.security

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Manages encrypted hardware-backed storage for sensitive server credentials
 * using Android KeyStore MasterKeys and EncryptedSharedPreferences (AES-256-GCM).
 */
class SecurityManager(context: Context) {

    private val sharedPreferences: SharedPreferences

    init {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()

        sharedPreferences = EncryptedSharedPreferences.create(
            context,
            PREFS_FILENAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SKEY_KEYGEN,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    var serverUrl: String
        get() = sharedPreferences.getString(KEY_SERVER_URL, "") ?: ""
        set(value) {
            val formatted = value.trim().trimEnd('/')
            sharedPreferences.edit().putString(KEY_SERVER_URL, formatted).apply()
        }

    var accessToken: String
        get() = sharedPreferences.getString(KEY_ACCESS_TOKEN, "") ?: ""
        set(value) {
            sharedPreferences.edit().putString(KEY_ACCESS_TOKEN, value.trim()).apply()
        }

    var isBiometricRequired: Boolean
        get() = sharedPreferences.getBoolean(KEY_BIOMETRIC_REQUIRED, false)
        set(value) {
            sharedPreferences.edit().putBoolean(KEY_BIOMETRIC_REQUIRED, value).apply()
        }

    fun isConfigured(): Boolean {
        return serverUrl.isNotEmpty()
    }

    fun clear() {
        sharedPreferences.edit().clear().apply()
    }

    companion object {
        private const val PREFS_FILENAME = "aimaos_secure_prefs"
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_ACCESS_TOKEN = "access_token"
        private const val KEY_BIOMETRIC_REQUIRED = "biometric_required"
    }
}
