[1st Error]

Console Error


A tree hydrated but some attributes of the server rendered HTML didn't match the client properties. This won't be patched up. This can happen if a SSR-ed Client Component used:
- A server/client branch `if (typeof window !== 'undefined')`.
- Variable input such as `Date.now()` or `Math.random()` which changes each time it's called.
- Date formatting in a user's locale which doesn't match the server.
- External changing data without sending a snapshot of it along with the HTML.
- Invalid HTML tag nesting.

It can also happen if the client has a browser extension installed which messes with the HTML before React loaded.

See more info here: https://nextjs.org/docs/messages/react-hydration-error


  ...
    <HotReload globalError={[...]} webSocket={WebSocket} staticIndicatorState={{pathname:null, ...}}>
      <AppDevOverlayErrorBoundary globalError={[...]}>
        <ReplaySsrOnlyErrors>
        <DevRootHTTPAccessFallbackBoundary>
          <HTTPAccessFallbackBoundary notFound={<NotAllowedRootHTTPFallbackError>}>
            <HTTPAccessFallbackErrorBoundary pathname="/" notFound={<NotAllowedRootHTTPFallbackError>} ...>
              <RedirectBoundary>
                <RedirectErrorBoundary router={{...}}>
                  <Head>
                  <__next_root_layout_boundary__>
                    <SegmentViewNode type="layout" pagePath="/DeepAgent...">
                      <SegmentTrieNode>
                      <link>
                      <script>
                      <RootLayout>
                        <html
                          lang="en"
+                         className="dark"
-                         className="dark hidden"
                        >
                  ...
src/app/layout.tsx (22:5) @ RootLayout


  20 | }>) {
  21 |   return (
> 22 |     <html lang="en" className="dark">
     |     ^
  23 |       <head>
  24 |         <link
  25 |           href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
Call Stack
18

Show 16 ignore-listed frame(s)
html
<anonymous>
RootLayout
src/app/layout.tsx (22:5)


[2nd Error]
Runtime TypeError



crypto.randomUUID is not a function
src/app/page.tsx (17:34) @ Home.useEffect


  15 |
  16 |   useEffect(() => {
> 17 |     threadIdRef.current = crypto.randomUUID();
     |                                  ^
  18 |   }, []);
  19 |
  20 |   const handleSend = useCallback(async (content: string) => {
Call Stack
51

Show 50 ignore-listed frame(s)
Home.useEffect
src/app/page.tsx (17:34)