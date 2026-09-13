package com.sd.budgetdashboard

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder

import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

import kotlin.concurrent.thread

class ServerService : Service() {

    companion object {
        private const val CHANNEL_ID = "server_channel"
        private const val NOTIFICATION_ID = 1001

        // MainActivity.kt reads this to show the real state instead of a
        // local "did I just click Start" flag, which goes stale (and
        // disagrees with the still-running notification) the moment the
        // Activity is recreated - e.g. reopening the app while the
        // foreground service kept running in the background the whole
        // time. Safe as a plain var: this service and MainActivity always
        // share one process (no android:process override in the manifest).
        var isRunning: Boolean = false
            private set
    }

    override fun onCreate() {
        super.onCreate()
        isRunning = true

        // Enter foreground immediately.
        createNotificationChannel()
        startForeground(
            NOTIFICATION_ID,
            createNotification()
        )

        // Start Python/FastAPI off the Android main thread.
        thread {
            startPythonServer()
        }
    }

    override fun onStartCommand(
        intent: Intent?,
        flags: Int,
        startId: Int
    ): Int {
        return START_STICKY
    }

    private fun startPythonServer() {

        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        val python = Python.getInstance()
        val serverModule = python.getModule("server")

        serverModule.callAttr("start_server")
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    override fun onDestroy() {
        super.onDestroy()
        isRunning = false
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Budget Dashboard",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps the read-only dashboard server running"
            }

            val manager =
                getSystemService(NotificationManager::class.java)

            manager.createNotificationChannel(channel)
        }
    }

    private fun createNotification(): Notification {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
                .setContentTitle("Budget Dashboard")
                .setContentText("Read-only dashboard server is running")
                .setSmallIcon(android.R.drawable.ic_menu_manage)
                .setOngoing(true)
                .build()
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
                .setContentTitle("Budget Dashboard")
                .setContentText("Read-only dashboard server is running")
                .setSmallIcon(android.R.drawable.ic_menu_manage)
                .setOngoing(true)
                .build()
        }
    }
}
