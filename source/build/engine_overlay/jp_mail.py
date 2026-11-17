"""JP mailbox guard; installed by android_game.start (2026-11-09).

The Global engine mails one "8th Anniversary Ticket" a day (ffbe_player.deliver_anniversary_ticket): item_type 20,
item 1209002123, a Global-only item. JP 11.0.0 F_ITEM_MST (Ver982_1CUX0Qwr, 3,851 rows) has no such item, and the
JP client crashed (SIGSEGV) right after the MailListRequest (KQHpi0D7) reply that listed it (test tablet 16:06 and
16:08). So: stop issuing the ticket, and drop mails already in the save that carry it.
"""
GL_ONLY_ITEMS = {1209002123}   # 8th Anniversary 10+1 Summon Ticket (Global only)


def install(server):
    import ffbe_player
    ffbe_player.ANNIVERSARY_TICKET = False
    player = server.State.player
    if player is None:
        print('JP mail: anniversary ticket off (no player yet)', flush=True)
        return
    before = list(player.mailbox)
    keep = [m for m in before
            if not any(int((it or {}).get('item_id') or 0) in GL_ONLY_ITEMS for it in (m.get('items') or []))]
    if len(keep) != len(before):
        player.data['mailbox'] = keep
        player.save(server.st.STATE_FILE, force=True)
    print('JP mail: anniversary ticket off, removed ' + str(len(before) - len(keep)) + ' Global-only mail(s)', flush=True)
