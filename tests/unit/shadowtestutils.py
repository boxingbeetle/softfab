# SPDX-License-Identifier: BSD-3-Clause

import shadowlib

class TestShadowRun(shadowlib.ShadowRun):
    tagName = 'test'

    @classmethod
    def create(cls):
        return cls._create()

    def _canBeRunOn(self, taskRunner):
        return taskRunner.getId().startswith('capable')
