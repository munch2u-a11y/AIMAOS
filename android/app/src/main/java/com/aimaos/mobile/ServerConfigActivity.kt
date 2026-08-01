package com.aimaos.mobile

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.aimaos.mobile.databinding.ActivityServerConfigBinding
import com.aimaos.mobile.security.SecurityManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

class ServerConfigActivity : AppCompatActivity() {

    private lateinit var binding: ActivityServerConfigBinding
    private lateinit var securityManager: SecurityManager

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityServerConfigBinding.inflate(layoutInflater)
        setContentView(binding.root)

        securityManager = SecurityManager(this)

        // Pre-fill existing settings if available
        binding.etServerUrl.setText(securityManager.serverUrl)
        binding.etAccessToken.setText(securityManager.accessToken)
        binding.switchBiometric.isChecked = securityManager.isBiometricRequired

        binding.btnSave.setOnClickListener {
            validateAndSave()
        }
    }

    private fun validateAndSave() {
        val rawUrl = binding.etServerUrl.text.toString().trim()
        val token = binding.etAccessToken.text.toString().trim()
        val requireBiometric = binding.switchBiometric.isChecked

        if (rawUrl.isEmpty()) {
            binding.tilServerUrl.error = "Server URL cannot be empty"
            return
        }
        binding.tilServerUrl.error = null

        val formattedUrl = if (!rawUrl.startsWith("http://") && !rawUrl.startsWith("https://")) {
            "http://$rawUrl"
        } else {
            rawUrl
        }.trimEnd('/')

        binding.tvStatus.visibility = View.VISIBLE
        binding.tvStatus.text = "Testing server connection & authentication..."
        binding.btnSave.isEnabled = false

        lifecycleScope.launch(Dispatchers.IO) {
            val (success, message) = testServerConnection(formattedUrl, token)
            withContext(Dispatchers.Main) {
                binding.btnSave.isEnabled = true
                if (success) {
                    securityManager.serverUrl = formattedUrl
                    securityManager.accessToken = token
                    securityManager.isBiometricRequired = requireBiometric

                    Toast.makeText(
                        this@ServerConfigActivity,
                        getString(R.string.success_connection),
                        Toast.LENGTH_SHORT
                    ).show()

                    val intent = Intent(this@ServerConfigActivity, MainActivity::class.java)
                    intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_NEW_TASK
                    startActivity(intent)
                    finish()
                } else {
                    binding.tvStatus.text = "Connection Failed: $message"
                    Toast.makeText(this@ServerConfigActivity, message, Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun testServerConnection(serverUrl: String, token: String): Pair<Boolean, String> {
        return try {
            val targetUrl = URL("$serverUrl/api/cases")
            val connection = targetUrl.openConnection() as HttpURLConnection
            connection.requestMethod = "GET"
            connection.connectTimeout = 5000
            connection.readTimeout = 5000
            if (token.isNotEmpty()) {
                connection.setRequestProperty("Authorization", "Bearer $token")
                connection.setRequestProperty("X-AIMAOS-Token", token)
            }

            val responseCode = connection.responseCode
            when (responseCode) {
                200 -> Pair(true, "Authentication successful")
                401 -> Pair(false, "Authentication Failed (401). Access Token (AIMAOS_UI_TOKEN) is invalid or missing.")
                403 -> Pair(false, "Access Forbidden (403).")
                else -> Pair(false, "Server responded with HTTP $responseCode")
            }
        } catch (e: Exception) {
            Pair(false, "Network error: ${e.localizedMessage}")
        }
    }
}
