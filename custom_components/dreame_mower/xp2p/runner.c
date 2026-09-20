/*
 * Live video helper for Dreame and MOVA mowers.
 *
 * The mower publishes its camera over Tencent's XP2P transport, whose client
 * library is a native x86-64 blob. This process negotiates one session and
 * exposes it as a local HTTP-FLV URL, so the integration itself stays pure
 * Python and never links against that library.
 *
 * Credentials arrive on stdin as key=value lines terminated by a blank line,
 * which keeps them out of the argument list and the environment:
 *
 *     product_id=...
 *     device_name=...
 *     p2p_info=...
 *     app_id=...
 *     app_secret=...
 *     <blank line>
 *
 * One line is then written to stdout, either
 *
 *     URL=http://127.0.0.1:<port>/.../ipc.flv?action=live&...
 *     ERROR=<reason>
 *
 * The session lives until stdin closes, so the caller owns its lifetime and
 * the helper cannot outlive Home Assistant.
 *
 * SPDX-License-Identifier: MIT
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "appWrapper.h"

#define MAX_VALUE 4096

/* Event 1004 means the peer link is up; 1005 means it failed. */
static volatile int g_ready;
static volatile int g_failed;

struct config {
    char product_id[256];
    char device_name[256];
    char p2p_info[MAX_VALUE];
    char app_id[256];
    char app_secret[256];
    char quality[32];
    int channel;
};

static const char *msg_cb(const char *id, XP2PType type, const char *msg)
{
    (void)id;
    switch (type) {
    case XP2PTypeDetectReady:
        g_ready = 1;
        break;
    case XP2PTypeDetectError:
        fprintf(stderr, "detect error: %s\n", msg ? msg : "");
        g_failed = 1;
        break;
    case XP2PTypeDisconnect:
        fprintf(stderr, "peer disconnected\n");
        break;
    case XP2PTypeStreamEnd:
        fprintf(stderr, "device stopped publishing\n");
        break;
    default:
        break;
    }
    return "";
}

static void av_cb(const char *id, uint8_t *buf, size_t len)
{
    /* Media is pulled over the local HTTP proxy, not through this callback. */
    (void)id; (void)buf; (void)len;
}

static void fail(const char *reason)
{
    printf("ERROR=%s\n", reason);
    fflush(stdout);
}

/* Copy one stdin value, refusing anything that would not fit. */
static int store(char *dst, size_t size, const char *value)
{
    size_t length = strlen(value);
    if (length == 0 || length >= size)
        return -1;
    memcpy(dst, value, length + 1);
    return 0;
}

static int read_config(struct config *cfg)
{
    char line[MAX_VALUE + 256];

    memcpy(cfg->quality, "high", sizeof("high"));

    while (fgets(line, sizeof(line), stdin)) {
        char *newline = strpbrk(line, "\r\n");
        if (newline)
            *newline = '\0';
        if (line[0] == '\0')
            return 0;

        char *separator = strchr(line, '=');
        if (!separator)
            continue;
        *separator = '\0';
        const char *key = line;
        const char *value = separator + 1;

        int bad = 0;
        if (!strcmp(key, "product_id"))
            bad = store(cfg->product_id, sizeof(cfg->product_id), value);
        else if (!strcmp(key, "device_name"))
            bad = store(cfg->device_name, sizeof(cfg->device_name), value);
        else if (!strcmp(key, "p2p_info"))
            bad = store(cfg->p2p_info, sizeof(cfg->p2p_info), value);
        else if (!strcmp(key, "app_id"))
            bad = store(cfg->app_id, sizeof(cfg->app_id), value);
        else if (!strcmp(key, "app_secret"))
            bad = store(cfg->app_secret, sizeof(cfg->app_secret), value);
        else if (!strcmp(key, "quality"))
            bad = store(cfg->quality, sizeof(cfg->quality), value);
        else if (!strcmp(key, "channel"))
            cfg->channel = atoi(value);

        if (bad) {
            fprintf(stderr, "value for %s is empty or too long\n", key);
            return -1;
        }
    }
    return -1;
}

int main(void)
{
    struct config cfg;
    memset(&cfg, 0, sizeof(cfg));

    if (read_config(&cfg) != 0) {
        fail("incomplete_request");
        return 2;
    }
    if (!cfg.product_id[0] || !cfg.device_name[0] || !cfg.p2p_info[0]
        || !cfg.app_id[0] || !cfg.app_secret[0]) {
        fail("incomplete_request");
        return 2;
    }

    char id[520];
    snprintf(id, sizeof(id), "%s/%s", cfg.product_id, cfg.device_name);
    fprintf(stderr, "xp2p sdk %s, session %s\n", VIDEOSDKVERSION, id);

    setUserCallbackToXp2p(av_cb, msg_cb, NULL);
    setLogEnable(false, false);

    app_config_t app_config;
    memset(&app_config, 0, sizeof(app_config));
    appGetDeviceConfig(id, cfg.product_id, cfg.device_name, cfg.app_id,
                       cfg.app_secret, &app_config);
    setCrossStunTurn(app_config.cross ? true : false);

    if (startService(id, cfg.product_id, cfg.device_name, cfg.p2p_info,
                     app_config) != 0) {
        fail("start_service_failed");
        return 3;
    }
    setDeviceXp2pInfo(id, cfg.p2p_info);

    /* Wait up to 60s for the peer link, polling so a failure exits early. */
    for (int i = 0; i < 600 && !g_ready && !g_failed; i++)
        usleep(100 * 1000);
    if (!g_ready) {
        fail(g_failed ? "peer_link_failed" : "peer_link_timeout");
        stopService(id);
        return 4;
    }

    /* The mower refuses media until it reports itself ready for this use. */
    char status_cmd[256];
    snprintf(status_cmd, sizeof(status_cmd),
             "action=inner_define&channel=%d&cmd=get_device_st&type=live"
             "&quality=standard", cfg.channel);
    unsigned char *reply = NULL;
    size_t reply_len = 0;
    int rc = postCommandRequestSync(id, (const unsigned char *)status_cmd,
                                    strlen(status_cmd), &reply, &reply_len, 0);
    fprintf(stderr, "device status rc=%d reply=%.*s\n", rc, (int)reply_len,
            reply ? (char *)reply : "");

    const char *prefix = delegateHttpFlv(id);
    if (!prefix) {
        fail("no_local_proxy");
        stopService(id);
        return 5;
    }

    printf("URL=%sipc.flv?action=live&channel=%d&quality=%s&_crypto=on\n",
           prefix, cfg.channel, cfg.quality);
    fflush(stdout);

    /* Hold the session open until the caller closes stdin. */
    while (getchar() != EOF)
        ;

    stopService(id);
    return 0;
}
