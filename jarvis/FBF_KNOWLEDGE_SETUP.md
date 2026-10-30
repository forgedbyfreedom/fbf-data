# Turn on the FBF knowledge base for phone Jarvis

Jarvis (the phone web app at data.forgedbyfreedom.org) can answer training,
nutrition, bloodwork, peptide, and program questions straight from YOUR Forged
by Freedom content instead of a model's generic, hedged answers.

The only thing standing in the way is a browser security rule: by default a page
on `data.forgedbyfreedom.org` isn't allowed to call `forgedbyfreedom.net`. We
fix that with one small snippet that tells WordPress "it's okay, let Jarvis in."

## Easiest way — Code Snippets plugin (2 minutes)

1. In WordPress admin, go to **Snippets → Add New** (if you don't have the free
   "Code Snippets" plugin, install it from Plugins → Add New first).
2. Title it `Jarvis CORS`, paste the PHP below, set it to **Run everywhere**, and
   click **Save and Activate**.

```php
<?php
// Allow the Jarvis phone app to call the FBF knowledge endpoint from the browser.
add_action('rest_api_init', function () {
    remove_filter('rest_pre_serve_request', 'rest_send_cors_headers');
    add_filter('rest_pre_serve_request', function ($served, $result, $request) {
        $allowed = array(
            'https://data.forgedbyfreedom.org',
            'https://forgedbyfreedom.github.io',
        );
        $origin = $request->get_header('origin');
        if ($origin && in_array($origin, $allowed, true)) {
            header('Access-Control-Allow-Origin: ' . $origin);
            header('Vary: Origin');
            header('Access-Control-Allow-Methods: POST, OPTIONS');
            header('Access-Control-Allow-Headers: Content-Type');
            if ('OPTIONS' === $request->get_method()) {
                status_header(204);
                exit;
            }
        }
        return $served;
    }, 10, 3);
}, 15);
```

## That's it

Once it's active, open Jarvis on your phone, make sure the **FBF knowledge base**
toggle is on in the gear menu, and ask a training or nutrition question — the
answer comes from your own material. (FBF answers show with an orange edge.)

If you'd rather not touch WordPress, the alternative is a tiny Cloudflare Worker
that relays the call — ask Jarvis and he'll write you the Worker code and paste
URL instead.
