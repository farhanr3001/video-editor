import copy,json,tempfile,unittest,urllib.request,urllib.error,concurrent.futures
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QEvent,QEventLoop,QTimer,QThreadPool
from PySide6.QtWidgets import QApplication
from kinetic_cut.model import Project,TimelineItem
from kinetic_cut.assistant_api import edited,revision
from kinetic_cut.assistant import register_codex, register_antigravity, antigravity_snippet
from kinetic_cut.mcp_bridge import send_mcp_request


class AssistantModelTests(unittest.TestCase):
    def test_atomic_batch_full_style_and_rollback(self):
        p=Project(); before=p.to_dict()
        result,ids=edited(p,[dict(op='add',collection='timeline',values=dict(title_text='Hello',fade_in=.4,title_style={'color':'#ff3344'}))])
        self.assertEqual(p.to_dict(),before); self.assertEqual(result.timeline[0].title_style.color,'#ff3344'); self.assertEqual(len(ids),1)
        with self.assertRaises(ValueError):edited(p,[dict(op='rename_project',name='Changed'),dict(op='bogus')])
        self.assertEqual(p.to_dict(),before)
    def test_nonfinite_and_invalid_media_rejected(self):
        for values in (dict(start=float('nan')),dict(duration=-1),dict(role='normal',media_id='missing'),dict(crop={'width':3})):
            with self.assertRaises((ValueError,TypeError)):edited(Project(),[dict(op='add',collection='timeline',values=values)])
    def test_revision_ignores_playhead_but_not_edits(self):
        p=Project(); original=revision(p); p.playhead=12; p.touch(); self.assertEqual(revision(p),original)
        p.name='Changed'; self.assertNotEqual(revision(p),original)
    def test_registration_preserves_other_servers_and_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.toml'; original='model = "example"\n[mcp_servers.other]\nurl = "http://localhost:12"\n'
            path.write_text(original); register_codex('http://127.0.0.1:9/mcp','test-token',path)
            first=path.read_text(); self.assertIn(original.strip(),first); self.assertEqual(first.count('[mcp_servers.kinetic_cut]'),1)
            register_codex('http://127.0.0.1:10/mcp','changed-token',path)
            self.assertEqual(path.read_text().count('[mcp_servers.kinetic_cut]'),1); self.assertTrue(list(Path(directory).glob('config.before-kinetic-cut-*.toml')))
    def test_antigravity_registration_preserves_other_servers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'mcp_config.json'
            original = {'mcpServers': {'existing-service': {'command': 'test-cmd', 'args': ['--arg']}}}
            path.write_text(json.dumps(original, indent=2))
            saved_path = register_antigravity(path=path)
            self.assertEqual(saved_path, str(path))
            data = json.loads(path.read_text())
            self.assertIn('existing-service', data['mcpServers'])
            self.assertIn('kinetic-cut', data['mcpServers'])
            kc = data['mcpServers']['kinetic-cut']
            self.assertIn('command', kc)
            self.assertIn('args', kc)

            # Test backup generation on modification
            register_antigravity(path=path, command='custom-python')
            data2 = json.loads(path.read_text())
            self.assertEqual(data2['mcpServers']['kinetic-cut']['command'], 'custom-python')
            self.assertTrue(list(Path(directory).glob('mcp_config.before-kinetic-cut-*.json')))

            # Test snippet
            snippet = antigravity_snippet()
            parsed_snippet = json.loads(snippet)
    def test_insert_clip_operation(self):
        p = Project()
        from kinetic_cut.model import MediaItem
        m = MediaItem('m1', 'dummy.mp4', 'video', 'dummy.mp4', 10.0, 1920, 1080, 30.0, True)
        p.add_media(m)
        result, ids = edited(p, [dict(op='insert_clip', media_id='m1', track='video_1', start=2.0, duration=4.0, in_point=1.0)])
        self.assertEqual(len(result.timeline), 1)
        self.assertEqual(result.timeline[0].start, 2.0)
        self.assertEqual(result.timeline[0].duration, 4.0)
        self.assertEqual(result.timeline[0].in_point, 1.0)
        self.assertEqual(result.timeline[0].track, 'video_1')

    def test_transitions_crud_and_insert_operation(self):
        p = Project()
        from kinetic_cut.model import MediaItem
        m = MediaItem('m1', 'dummy.mp4', 'video', 'dummy.mp4', 10.0, 1920, 1080, 30.0, True)
        p.add_media(m)
        # Add 2 clips
        res, ids = edited(p, [
            dict(op='insert_clip', media_id='m1', track='video_1', start=0.0, duration=3.0, in_point=0.0),
            dict(op='insert_clip', media_id='m1', track='video_1', start=3.0, duration=3.0, in_point=3.0),
        ])
        c1_id, c2_id = ids[0], ids[1]

        # Insert transition via op='insert_transition'
        res2, t_ids = edited(res, [
            dict(op='insert_transition', name='Dip to Color / White Flash', track='video_1',
                 left_item_id=c1_id, right_item_id=c2_id, duration=0.6, alignment='center',
                 properties={'flash_color': '#ff0000'})
        ])
        self.assertEqual(len(res2.transitions), 1)
        tr = res2.transitions[0]
        self.assertEqual(tr.name, 'Dip to Color / White Flash')
        self.assertEqual(tr.category, 'Dissolve')
        self.assertEqual(tr.track, 'video_1')
        self.assertEqual(tr.duration, 0.6)
        self.assertAlmostEqual(tr.start, 2.7)  # 3.0 - 0.6/2
        self.assertEqual(tr.properties.get('flash_color'), '#ff0000')

        # Update transition via op='update', collection='transitions'
        res3, _ = edited(res2, [
            dict(op='update', collection='transitions', id=tr.id, values={'duration': 1.0, 'alignment': 'start'})
        ])
        self.assertEqual(res3.transitions[0].duration, 1.0)
        self.assertEqual(res3.transitions[0].alignment, 'start')

        # Remove transition via op='remove', collection='transitions'
        res4, _ = edited(res3, [
            dict(op='remove', collection='transitions', id=tr.id)
        ])
        self.assertEqual(len(res4.transitions), 0)

        # Invalid duration rejection
        with self.assertRaises(ValueError):
            edited(res, [dict(op='insert_transition', name='Cross Dissolve', duration=0.01)])


class AssistantLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from kinetic_cut.ui import MainWindow
        self.app = QApplication.instance()
        self.w = MainWindow()
        self.w.show()
        self.w.autosave_timer.stop()
        self.c = self.w.assistant_connection
        self.c.config['port']=0; self.c.start(); self.assertIsNotNone(self.c.server); self.pool=concurrent.futures.ThreadPoolExecutor(2)
    def tearDown(self):
        self.c.stop(); self.pool.shutdown(wait=True); self.w.close(); QThreadPool.globalInstance().waitForDone(10000); self.w.deleteLater(); self.app.sendPostedEvents(None,QEvent.DeferredDelete); self.app.processEvents()
    def request(self,method,params=None,headers=None):
        data=json.dumps(dict(jsonrpc='2.0',id=1,method=method,params=params or {})).encode()
        h={'Authorization':'Bearer '+self.c.config['token'],'Content-Type':'application/json','Accept':'application/json, text/event-stream'}; h.update(headers or {})
        request=urllib.request.Request(self.c.server.url,data=data,headers=h)
        future=self.pool.submit(lambda:json.loads(urllib.request.urlopen(request,timeout=12).read()))
        loop=QEventLoop(); timer=QTimer(); timer.timeout.connect(lambda:loop.quit() if future.done() else None); timer.start(5); QTimer.singleShot(14000,loop.quit); loop.exec(); timer.stop()
        return future.result(timeout=1)
    def call(self,_tool_name,**arguments):
        result=self.request('tools/call',dict(name=_tool_name,arguments=arguments))['result']
        if result.get('isError'):raise ValueError(result['content'][0]['text'])
        return result
    def test_handshake_list_edit_preview_undo_over_real_http(self):
        result=self.request('initialize',dict(protocolVersion='2025-06-18',clientInfo=dict(name='MCP integration test',version='1'),capabilities={}))
        self.assertEqual(result['result']['serverInfo']['name'],'Kinetic Cut'); self.assertEqual(self.c.client,'MCP integration test')
        names={t['name'] for t in self.request('tools/list')['result']['tools']}; self.assertIn('get_preview',names); self.assertIn('ui_control',names)
        self.call('apply_edits',revision=revision(self.w.project),operations=[dict(op='add',collection='timeline',values=dict(title_text='MCP edit'))])
        self.assertEqual(self.w.project.timeline[0].title_text,'MCP edit'); self.assertEqual(len(self.w._history),2)
        image=self.call('get_preview')['content'][1]; self.assertEqual(image['type'],'image'); self.assertGreater(len(image['data']),100)
        self.call('history',direction='undo'); self.assertFalse(self.w.project.timeline)
    def test_unauthorized_origin_and_invalid_version_rejected(self):
        for headers in ({'Authorization':'Bearer wrong'},{'Origin':'https://hostile.example'},{'MCP-Protocol-Version':'invalid'}):
            with self.assertRaises(urllib.error.HTTPError):self.request('tools/list',headers=headers)
    def test_stale_revision_and_invalid_batch_do_not_mutate(self):
        before=self.w.project.to_dict()
        with self.assertRaisesRegex(ValueError,'changed'):self.call('apply_edits',revision='stale',operations=[dict(op='rename_project',name='bad')])
        with self.assertRaises(ValueError):self.call('apply_edits',revision=revision(self.w.project),operations=[dict(op='rename_project',name='bad'),dict(op='invalid')])
        self.assertEqual(before,self.w.project.to_dict())
    def test_panel_is_connection_only_and_ui_controls_work(self):
        self.c.show(); self.app.processEvents(); self.assertIn('MCP Connection',self.c.dialog.windowTitle())
        controls=json.loads(self.call('inspect_ui')['content'][0]['text'])['controls']
        self.assertTrue(any(c['text']=='Connect to Codex' for c in controls))
        target=next(c['target'] for c in controls if c['text']=='Enable this connection whenever Kinetic Cut opens')
        with patch('kinetic_cut.config.save_settings'):self.call('ui_control',target=target,operation='set',value=True)
        self.assertTrue(self.c.dialog.auto.isChecked())

    def test_startup_flags_never_open_panel_and_badge_requires_client(self):
        from kinetic_cut.assistant import configure_startup_connection
        self.assertIsNone(self.c.dialog); self.assertFalse(self.c.verified)
        with patch('kinetic_cut.config.save_settings'),patch('kinetic_cut.assistant.register_codex'):
            configure_startup_connection(self.w,['--enable-mcp']); configure_startup_connection(self.w,['--connect-codex'])
        self.assertIsNone(self.c.dialog); self.assertFalse(self.w.assistant_button.property('clientVerified'))
        self.request('initialize',dict(protocolVersion='2025-06-18',clientInfo=dict(name='Codex',version='1')))
        self.assertTrue(self.c.verified); self.assertTrue(self.w.assistant_button.property('clientVerified')); self.assertIsNone(self.c.dialog)
        self.c.show(); self.app.processEvents(); self.assertTrue(self.c.dialog.status_icon.isVisible()); self.assertIn('Codex',self.c.dialog.status.text())
        self.c.stop(); self.assertFalse(self.w.assistant_button.property('clientVerified')); self.assertFalse(self.c.dialog.status_icon.isVisible())

    def test_authenticated_reused_tool_list_and_ping_verify_client(self):
        self.request('tools/list'); self.assertTrue(self.c.verified); self.assertEqual(self.c.client,'MCP client')
        self.assertIsNone(self.c.dialog); self.c.last_seen=0
        self.request('ping'); self.assertGreater(self.c.last_seen,0); self.assertTrue(self.c.verified)

    def test_mcp_bridge_and_antigravity_controls(self):
        self.c.show(); self.app.processEvents()
        controls = json.loads(self.call('inspect_ui')['content'][0]['text'])['controls']
        self.assertTrue(any(c['text'] == 'Connect to Antigravity' for c in controls))
        self.assertTrue(any(c['text'] == 'Connect to Codex' for c in controls))
        self.assertTrue(any(c['text'] == 'Copy Antigravity JSON' for c in controls))

        def send_via_pool(payload):
            future = self.pool.submit(lambda: send_mcp_request(self.c.server.url, self.c.config['token'], payload))
            loop = QEventLoop(); timer = QTimer(); timer.timeout.connect(lambda: loop.quit() if future.done() else None); timer.start(5); QTimer.singleShot(14000, loop.quit); loop.exec(); timer.stop()
            return future.result(timeout=1)

        init_req = {
            'jsonrpc': '2.0',
            'id': 100,
            'method': 'initialize',
            'params': {
                'protocolVersion': '2025-11-25',
                'clientInfo': {'name': 'Antigravity IDE', 'version': '2.0'},
                'capabilities': {}
            }
        }
        resp = send_via_pool(init_req)
        self.assertIsNotNone(resp)
        self.assertEqual(resp['id'], 100)
        self.assertEqual(resp['result']['serverInfo']['name'], 'Kinetic Cut')
        self.assertEqual(self.c.client, 'Antigravity IDE')

        tools_req = {'jsonrpc': '2.0', 'id': 101, 'method': 'tools/list', 'params': {}}
        tools_resp = send_via_pool(tools_req)
        self.assertIsNotNone(tools_resp)
        names = {t['name'] for t in tools_resp['result']['tools']}
        self.assertIn('get_state', names)
        self.assertIn('apply_edits', names)
        self.assertIn('import_media', names)

    def test_new_automation_tools_and_commands(self):
        names = {t['name'] for t in self.request('tools/list')['result']['tools']}
        self.assertIn('synthesize_dialogue', names)
        self.assertIn('apply_visual_fx', names)
        self.assertIn('get_timeline_summary', names)
        self.assertIn('download_media', names)

        def val(name, **kwargs):
            r = self.call(name, **kwargs)
            return json.loads(r['content'][0]['text'])

        from kinetic_cut.model import MediaItem
        m = MediaItem('v1', 'test.mp4', 'video', 'test.mp4', 15.0, 1920, 1080, 30.0, False)
        self.w.project.add_media(m)
        res = val('apply_edits', revision=revision(self.w.project), operations=[
            dict(op='insert_clip', media_id='v1', track='video_1', start=1.0, duration=5.0, in_point=2.0)
        ])
        clip_id = res['created_ids'][0]
        self.assertEqual(self.w.project.timeline[0].id, clip_id)
        self.assertEqual(self.w.project.timeline[0].start, 1.0)
        self.assertEqual(self.w.project.timeline[0].duration, 5.0)

        fx_res = val('apply_visual_fx', item_id=clip_id, effect='Punch Zoom', properties={'target_zoom': 1.75, 'duration': 0.6})
        self.assertEqual(fx_res['effect'], 'Punch Zoom')
        self.assertEqual(fx_res['properties']['target_zoom'], 1.75)
        self.assertEqual(fx_res['properties']['duration'], 0.6)
        self.assertEqual(len(self.w.project.timeline[0].effects), 1)

        summary = val('get_timeline_summary')
        self.assertEqual(len(summary['video_tracks']), 1)
        self.assertEqual(summary['video_tracks'][0]['clips'][0]['id'], clip_id)
        self.assertIn('Punch Zoom', summary['video_tracks'][0]['clips'][0]['effects'])

        caps = val('get_capabilities')
        self.assertIn('generate_tts_dialogue', caps['commands'])
        self.assertIn('apply_visual_fx', caps['commands'])
        self.assertIn('set_caption_style', caps['commands'])
        self.assertIn('apply_vertical_framing', caps['commands'])
        self.assertIn('download_media', caps['commands'])

        # Test set_caption_style tool with viral_yellow preset and custom override
        style_res = val('set_caption_style', preset='crime_red', properties={'size': 66})
        self.assertEqual(style_res['style']['font'], 'Anton')
        self.assertEqual(style_res['style']['color'], '#FFFFFF')
        self.assertEqual(style_res['style']['size'], 66)
        self.assertEqual(style_res['style']['highlight'], '#FF2233')
        self.assertEqual(self.w.project.subtitle_style.font, 'Anton')
        self.assertEqual(self.w.project.subtitle_style.size, 66)

        # Test apply_vertical_framing tool
        frame_res = val('apply_vertical_framing', mode='center_and_fill', foreground_track='video_1', background_track='video_2', scale=1.45)
        self.assertEqual(frame_res['result']['foreground_count'], 1)
        self.assertEqual(self.w.project.timeline[0].transform.y, 0.5)
        self.assertAlmostEqual(self.w.project.timeline[0].transform.scale, 1.45)

        # Test download_media tool
        with patch('kinetic_cut.downloader_dialog.download_media_synchronous') as mock_dl:
            mock_dl.return_value = {
                'path': 'mock_short.mp4',
                'name': 'mock_short.mp4',
                'title': 'Mock Short',
                'mode': 'video',
                'size_bytes': 4096
            }
            dl_res = val('download_media', url='https://www.youtube.com/shorts/test123', auto_import=False, wait=True)
            self.assertTrue(dl_res['ok'])
            self.assertEqual(dl_res['name'], 'mock_short.mp4')
            self.assertEqual(dl_res['mode'], 'video')

            job_res = val('download_media', url='https://www.youtube.com/shorts/test123', auto_import=False, wait=False)
            self.assertEqual(job_res['state'], 'Running')

    def test_rapid_undo_resilience(self):
        from kinetic_cut.model import MediaItem, TimelineItem
        m = MediaItem('m_undo', 'test.mp4', 'video', 'test.mp4', 100.0, 1920, 1080, 30.0, True)
        self.w.project.add_media(m)
        # Build up multiple history snapshots
        for i in range(10):
            item = TimelineItem(id=f"test_clip_{i}", media_id='m_undo', track='video_1', start=float(i * 3), duration=2.5)
            self.w.project.timeline.append(item)
            self.w.commit_history()

        initial_len = len(self.w.project.timeline)
        self.assertGreater(initial_len, 5)

        # Rapidly fire 35 undos in succession without waiting (simulating holding Ctrl+Z)
        for _ in range(35):
            self.w.undo()

        self.app.processEvents()
        self.assertGreaterEqual(self.w._history_index, 0)
        self.assertIsNotNone(self.w.project)
        self.assertTrue(hasattr(self.w.project, 'timeline'))

    def test_transitions_and_graphics_automation(self):
        names = {t['name'] for t in self.request('tools/list')['result']['tools']}
        self.assertIn('apply_transition', names)
        self.assertIn('add_graphic', names)

        def val(tool_cmd, **kwargs):
            r = self.call(tool_cmd, **kwargs)
            return json.loads(r['content'][0]['text'])

        from kinetic_cut.model import MediaItem
        m = MediaItem('v_trans', 'test_trans.mp4', 'video', 'test_trans.mp4', 20.0, 1920, 1080, 30.0, False)
        self.w.project.add_media(m)

        # 1. Insert 2 adjacent clips
        res = val('apply_edits', revision=revision(self.w.project), operations=[
            dict(op='insert_clip', media_id='v_trans', track='video_1', start=0.0, duration=4.0, in_point=0.0),
            dict(op='insert_clip', media_id='v_trans', track='video_1', start=4.0, duration=4.0, in_point=4.0),
        ])
        c1, c2 = res['created_ids'][0], res['created_ids'][1]

        # 2. Apply transition via apply_transition tool
        tr_res = val('apply_transition', name='Cross Dissolve', track='video_1', left_item_id=c1, right_item_id=c2,
                     duration=0.8, alignment='center', properties={'blur_radius': 12.0})
        self.assertEqual(tr_res['name'], 'Cross Dissolve')
        self.assertEqual(tr_res['category'], 'Dissolve')
        self.assertEqual(tr_res['track'], 'video_1')
        self.assertEqual(tr_res['duration'], 0.8)
        self.assertAlmostEqual(tr_res['start'], 3.6)
        self.assertEqual(tr_res['properties']['blur_radius'], 12.0)
        self.assertEqual(len(self.w.project.transitions), 1)
        trans_id = tr_res['transition_id']

        # 3. get_state reports selected_transition_id
        state = val('get_state', section='summary')
        self.assertEqual(state['selected_transition_id'], trans_id)

        # 4. get_timeline_summary includes transitions
        summary = val('get_timeline_summary')
        self.assertIn('transitions', summary)
        self.assertEqual(len(summary['transitions']), 1)
        self.assertEqual(summary['transitions'][0]['id'], trans_id)
        self.assertEqual(summary['transitions'][0]['name'], 'Cross Dissolve')
        self.assertEqual(summary['transitions'][0]['left_item_id'], c1)
        self.assertEqual(summary['transitions'][0]['right_item_id'], c2)

        # 5. add_graphic tool
        g_res = val('add_graphic', graphic_type='Timer / Countdown', track='video_1', start=2.0, duration=5.0,
                    properties={'countdown_mode': 'Countdown', 'font_glow': True})
        self.assertEqual(g_res['graphic_type'], 'Timer / Countdown')
        self.assertEqual(g_res['track'], 'video_1')
        self.assertEqual(g_res['duration'], 5.0)
        self.assertTrue(g_res['properties'].get('font_glow'))
        self.assertEqual(len([i for i in self.w.project.timeline if i.role == 'graphic']), 1)

        # 6. select_items with transition_id
        sel_res = val('select_items', transition_id=trans_id)
        self.assertEqual(sel_res['transition_id'], trans_id)
        self.assertEqual(self.w.timeline.selected_transition_id, trans_id)

        # 7. remove_transition via editor_command
        self.w.remove_transition(trans_id)
        self.assertEqual(len(self.w.project.transitions), 0)

        # 8. add_audio_track
        orig_audio_tracks = len(self.w.project.audio_tracks)
        new_track = self.w.add_audio_track()
        self.assertEqual(len(self.w.project.audio_tracks), orig_audio_tracks + 1)
        self.assertIn(new_track, self.w.project.audio_tracks)



