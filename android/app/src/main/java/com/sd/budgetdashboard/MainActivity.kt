package com.sd.budgetdashboard

import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Bundle
import android.util.Log
import androidx.activity.compose.setContent
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.chaquo.python.PyException
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONArray
import java.net.Inet4Address
import java.net.NetworkInterface

// FragmentActivity, not ComponentActivity - BiometricPrompt requires it.
class MainActivity : FragmentActivity() {

    // Re-locks whenever the app leaves the foreground (see onPause) - a
    // banking-app-style re-prompt, not just a one-time gate at process
    // start, since the whole point is that picking up the phone later
    // shouldn't land straight back on this screen unlocked.
    private val unlocked = mutableStateOf(false)

    // The LAN password (see android_dashboard/auth.py) is separate from the
    // biometric lock above: the biometric lock guards this control screen on
    // the phone itself, the LAN password guards the actual HTTP server every
    // other device on the Wi-Fi talks to. Server.py's middleware fails
    // CLOSED until one is set, so this screen is shown ahead of the
    // dashboard controls the very first time, and reachable again afterwards
    // to change it.
    private val passwordSet = mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Started here (not only in ServerService) so the password/viewer
        // screens below work even before the server has ever been started -
        // Chaquopy's interpreter is one process-wide instance either way.
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        setContent {
            when {
                !unlocked.value -> LockScreen(onUnlock = { authenticate() })
                !passwordSet.value -> SetPasswordScreen(
                    isChange = false,
                    onSaved = { passwordSet.value = true },
                    onCancel = null,
                )
                else -> ServerDashboard()
            }
        }
    }

    override fun onStart() {
        super.onStart()
        if (!unlocked.value) authenticate()
    }

    override fun onPause() {
        super.onPause()
        // Re-lock on the way out - authenticate() runs again in onStart the
        // next time this activity comes back to the foreground.
        unlocked.value = false
    }

    private fun authenticate() {
        val biometricManager = BiometricManager.from(this)
        val allowedAuthenticators = BIOMETRIC_WEAK or DEVICE_CREDENTIAL
        when (biometricManager.canAuthenticate(allowedAuthenticators)) {
            BiometricManager.BIOMETRIC_SUCCESS -> showBiometricPrompt(allowedAuthenticators)
            else -> {
                // No fingerprint/face enrolled and no screen lock set up at
                // all - this is a personal, single-owner phone, so fail
                // OPEN rather than permanently locking the owner out of
                // their own app over a device they haven't configured a
                // lock on yet.
                Log.w("MainActivity", "Biometric/device-credential auth unavailable - skipping lock")
                onUnlocked()
            }
        }
    }

    private fun showBiometricPrompt(allowedAuthenticators: Int) {
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(
            this, executor,
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    onUnlocked()
                }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    // User cancelled, or too many failed attempts, etc. -
                    // stay locked; LockScreen's button lets them retry.
                }
                override fun onAuthenticationFailed() {
                    // A single wrong fingerprint/face match - the system
                    // prompt itself already handles retry UI, nothing to
                    // do here beyond staying locked.
                }
            },
        )
        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Unlock Budget Dashboard")
            .setSubtitle("Authenticate to view the server controls")
            .setAllowedAuthenticators(allowedAuthenticators)
            .build()
        prompt.authenticate(promptInfo)
    }

    private fun onUnlocked() {
        unlocked.value = true
        passwordSet.value = isPasswordSetPy()
    }

    private fun startServer() {
        val intent = Intent(this, ServerService::class.java)
        startForegroundService(intent)
    }

    private fun stopServer() {
        val intent = Intent(this, ServerService::class.java)
        stopService(intent)
    }

    @Composable
    fun LockScreen(onUnlock: () -> Unit) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background
        ) {
            Column(
                modifier = Modifier.fillMaxSize().padding(24.dp),
                verticalArrangement = Arrangement.Center
            ) {
                Text(text = "Budget Dashboard", style = MaterialTheme.typography.headlineMedium)
                Spacer(modifier = Modifier.height(8.dp))
                Text(text = "Locked - authenticate to continue", style = MaterialTheme.typography.bodyLarge)
                Spacer(modifier = Modifier.height(24.dp))
                Button(onClick = onUnlock) {
                    Text("Unlock")
                }
            }
        }
    }

    @Composable
    fun SetPasswordScreen(isChange: Boolean, onSaved: () -> Unit, onCancel: (() -> Unit)?) {
        var password by remember { mutableStateOf("") }
        var confirm by remember { mutableStateOf("") }
        var error by remember { mutableStateOf<String?>(null) }

        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
            Column(
                modifier = Modifier.fillMaxSize().padding(24.dp),
                verticalArrangement = Arrangement.Center,
            ) {
                Text(
                    text = if (isChange) "Change LAN Password" else "Set a LAN Password",
                    style = MaterialTheme.typography.headlineSmall,
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Anyone on your Wi-Fi who knows this password can open your dashboard in a " +
                        "browser. It's separate from unlocking this app, and required before the server " +
                        "will respond to anything.",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(modifier = Modifier.height(20.dp))
                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it; error = null },
                    label = { Text("New password") },
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = confirm,
                    onValueChange = { confirm = it; error = null },
                    label = { Text("Confirm password") },
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                )
                error?.let {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
                Spacer(modifier = Modifier.height(16.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(onClick = {
                        when {
                            password.length < 4 -> error = "Password must be at least 4 characters"
                            password != confirm -> error = "Passwords don't match"
                            else -> try {
                                setPasswordPy(password)
                                onSaved()
                            } catch (e: PyException) {
                                error = e.message ?: "Couldn't save the password"
                            }
                        }
                    }) { Text("Save") }
                    if (onCancel != null) {
                        Button(onClick = onCancel) { Text("Cancel") }
                    }
                }
            }
        }
    }

    @Composable
    fun ManageViewersSection() {
        var usersJson by remember { mutableStateOf(loadUsersJsonPy()) }
        var name by remember { mutableStateOf("") }
        var spreadsheetId by remember { mutableStateOf("") }
        var error by remember { mutableStateOf<String?>(null) }

        val userNames = remember(usersJson) {
            val arr = JSONArray(usersJson)
            (0 until arr.length()).map { i -> arr.getJSONObject(i).getString("name") }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text("Viewers", style = MaterialTheme.typography.titleLarge)
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Anyone listed here shows up in the dashboard's profile switcher, each with " +
                        "its own isolated local cache. The same reader account needs Viewer access on " +
                        "their spreadsheet first (see README.md).",
                    style = MaterialTheme.typography.bodySmall,
                )
                Spacer(modifier = Modifier.height(12.dp))
                if (userNames.isEmpty()) {
                    Text("No viewers yet.", style = MaterialTheme.typography.bodyMedium)
                } else {
                    userNames.forEach { u ->
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(u, style = MaterialTheme.typography.bodyLarge)
                            TextButton(onClick = {
                                try {
                                    removeUserPy(u)
                                    usersJson = loadUsersJsonPy()
                                } catch (e: PyException) {
                                    error = e.message ?: "Couldn't remove $u"
                                }
                            }) { Text("Remove") }
                        }
                    }
                }
                Spacer(modifier = Modifier.height(12.dp))
                OutlinedTextField(
                    value = name, onValueChange = { name = it; error = null },
                    label = { Text("Name") }, modifier = Modifier.fillMaxWidth(),
                )
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(
                    value = spreadsheetId, onValueChange = { spreadsheetId = it; error = null },
                    label = { Text("Spreadsheet ID") }, modifier = Modifier.fillMaxWidth(),
                )
                error?.let {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
                Spacer(modifier = Modifier.height(8.dp))
                Button(onClick = {
                    try {
                        addUserPy(name, spreadsheetId)
                        name = ""
                        spreadsheetId = ""
                        usersJson = loadUsersJsonPy()
                    } catch (e: PyException) {
                        error = e.message ?: "Couldn't add viewer"
                    }
                }) { Text("Add Viewer") }
            }
        }
    }

    @Composable
    fun ServerDashboard() {
        // Read from ServerService.isRunning (not a local "did I just click
        // Start" flag) so this reflects reality even after the Activity is
        // recreated while the foreground service kept running - see that
        // companion property's own comment for why a plain var is safe here.
        var serverRunning by remember { mutableStateOf(ServerService.isRunning) }
        var changingPassword by remember { mutableStateOf(false) }
        val clipboard = LocalClipboardManager.current

        val ipAddress = remember {
            getLocalIpAddress()
        }

        if (changingPassword) {
            SetPasswordScreen(
                isChange = true,
                onSaved = { changingPassword = false },
                onCancel = { changingPassword = false },
            )
            return
        }

        Surface(
            modifier = Modifier.fillMaxSize(),
            color = MaterialTheme.colorScheme.background
        ) {
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(24.dp),
                verticalArrangement = Arrangement.Top
            ) {

                Text(
                    text = "Budget Dashboard",
                    style = MaterialTheme.typography.headlineMedium
                )

                Text(
                    text = "Local server host",
                    style = MaterialTheme.typography.bodyLarge
                )

                Spacer(modifier = Modifier.height(24.dp))

                Card(
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp)
                    ) {
                        Text(
                            text = "Server Status",
                            style = MaterialTheme.typography.titleLarge
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        Text(
                            text = if (serverRunning) {
                                "● Running"
                            } else {
                                "● Stopped"
                            }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                Card(
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp)
                    ) {
                        Text(
                            text = "Server Information",
                            style = MaterialTheme.typography.titleLarge
                        )

                        Spacer(modifier = Modifier.height(12.dp))

                        Text("Host: 0.0.0.0")
                        Text("Port: 8000")
                        Text("Runtime: Python 3.13")
                        Text("Framework: FastAPI")
                        Text("Server: Uvicorn")

                        Spacer(modifier = Modifier.height(16.dp))

                        Text(
                            text = "LAN Address",
                            style = MaterialTheme.typography.titleMedium
                        )

                        Spacer(modifier = Modifier.height(4.dp))

                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = "$ipAddress:8000",
                                style = MaterialTheme.typography.headlineSmall,
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            TextButton(onClick = {
                                clipboard.setText(AnnotatedString("http://$ipAddress:8000"))
                            }) { Text("Copy") }
                        }

                        Spacer(modifier = Modifier.height(4.dp))

                        Text(
                            text = "Open this address on another device " +
                                    "connected to the same Wi-Fi."
                        )
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Text("LAN Password", style = MaterialTheme.typography.titleLarge)
                        Spacer(modifier = Modifier.height(8.dp))
                        Text("Required before the server will respond to anything on the network.")
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(onClick = { changingPassword = true }) { Text("Change Password") }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))

                ManageViewersSection()

                Spacer(modifier = Modifier.height(24.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {

                    Button(
                        onClick = {
                            startServer()
                            serverRunning = true
                        },
                        enabled = !serverRunning,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Start Server")
                    }

                    Button(
                        onClick = {
                            stopServer()
                            serverRunning = false
                        },
                        enabled = serverRunning,
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Stop Server")
                    }
                }
            }
        }
    }
}

private fun pyModule(name: String) = Python.getInstance().getModule(name)

private fun isPasswordSetPy(): Boolean =
    pyModule("android_dashboard.auth").callAttr("is_password_set").toBoolean()

private fun setPasswordPy(password: String) {
    pyModule("android_dashboard.auth").callAttr("set_password", password)
}

private fun loadUsersJsonPy(): String =
    pyModule("android_dashboard.users_config").callAttr("load_users_json").toString()

private fun addUserPy(name: String, spreadsheetId: String) {
    pyModule("android_dashboard.users_config").callAttr("add_user", name, spreadsheetId)
}

private fun removeUserPy(name: String) {
    pyModule("android_dashboard.users_config").callAttr("remove_user", name)
}

private fun getLocalIpAddress(): String {
    return try {
        val interfaces = NetworkInterface.getNetworkInterfaces()

        while (interfaces.hasMoreElements()) {
            val networkInterface = interfaces.nextElement()

            if (!networkInterface.isUp || networkInterface.isLoopback) {
                continue
            }

            val addresses = networkInterface.inetAddresses

            while (addresses.hasMoreElements()) {
                val address = addresses.nextElement()

                if (address is Inet4Address && !address.isLoopbackAddress) {
                    return address.hostAddress ?: "Unknown"
                }
            }
        }

        "Not connected"
    } catch (e: Exception) {
        "Unknown"
    }
}
