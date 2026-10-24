/**
 * The plan being composed: its robots and their steps, its objects, and which robot is
 * edited; the plan document is kept in the protocol's JSON form, so it is what is saved,
 * generated and run.
 */

import {
  ActionFieldKey,
  ActionFieldKind,
  ActionSchemaKey,
  DestinationKey,
  ObjectModelKey,
  PlacementMode,
  PlanBuilderCatalogKey,
  PlanBuilderLimitsKey,
  PlanKey,
  PlannedObjectKey,
  PlannedRobotKey,
  PlanStepKey,
  RobotModelKey,
  StepConstraintKey,
} from '../../../protocol.js';
import { PlanPose } from './poses.js';

/**
 * The name of a new plan.
 */
export const NEW_PLAN_NAME = 'new_plan';

/**
 * The prefixes of the identities the builder gives robots and steps.
 */
export const IdentityPrefix = Object.freeze({ ROBOT: 'robot_', STEP: 'step_', OBJECT: 'object_' });

/**
 * What an object identity may hold; other characters of a model's name become `_`.
 */
const NON_IDENTITY_CHARACTERS = /[^A-Za-z0-9_]+/g;

/**
 * What an object identity must start with.
 */
const IDENTITY_START = /^[A-Za-z]/;

/**
 * Where new robots stand, in metres: the first at the origin, the next beside it.
 */
const ROBOT_SPACING = 1.5;

/**
 * Where the builder puts what it adds relative to the robot, in metres.
 */
const Placement = Object.freeze({
  TARGET_AHEAD: 1.0,
  NEXT_TARGET_STEP: 0.4,
  OBJECT_AHEAD: 0.7,
  OBJECT_HEIGHT: 0.8,
  OBJECT_SPREAD: 0.15,
  PUT_DOWN_BESIDE: 0.3,
});

/**
 * The field kinds whose values are poses, alone or inside a destination.
 */
const POSE_KINDS = Object.freeze([ActionFieldKind.POSE, ActionFieldKind.POSE_OR_SURFACE]);

/**
 * The field kinds whose value is a plain JSON value of one type, with the type it has.
 */
const PLAIN_TYPES = Object.freeze({
  [ActionFieldKind.NUMBER]: 'number',
  [ActionFieldKind.INTEGER]: 'number',
  [ActionFieldKind.BOOLEAN]: 'boolean',
  [ActionFieldKind.TEXT]: 'string',
  [ActionFieldKind.ANNOTATION]: 'string',
});

// %% errors

/**
 * A change the catalog or the limits do not allow.
 */
export class PlanRefused extends Error {}

// %% state

export class PlanState {
  /**
   * The catalog the plan is composed from.
   * @type {Object}
   */
  #catalog;

  /**
   * The plan document.
   * @type {Object}
   */
  #plan;

  /**
   * The identity of the robot whose steps are edited.
   * @type {string|null}
   */
  #activeRobot;

  /**
   * @param {Object} catalog The plan builder's catalog.
   * @param {Object} plan A plan document.
   */
  constructor(catalog, plan) {
    this.#catalog = catalog;
    this.#plan = structuredClone(plan);
    this.#plan[PlanKey.ROBOTS] ??= [];
    this.#plan[PlanKey.OBJECTS] ??= [];
    for (const robot of this.#plan[PlanKey.ROBOTS]) {
      robot[PlannedRobotKey.STEPS] ??= [];
      for (const step of robot[PlannedRobotKey.STEPS]) {
        step[PlanStepKey.VALUES] ??= {};
        step[PlanStepKey.CONSTRAINTS] ??= [];
      }
    }
    this.#activeRobot = plan[PlanKey.SELECTED_ROBOT] ?? this.robots()[0]?.[PlannedRobotKey.IDENTIFIER] ?? null;
  }

  /**
   * @param {Object} catalog The plan builder's catalog.
   * @param {string|null} environment The environment bundle, or null for an empty floor.
   * @param {string|null=} preferred The robot model to start with when the catalog has
   *   it.
   * @returns {PlanState} A new plan with one robot: of the preferred model, else of the
   *   model offering the most actions.
   */
  static empty(catalog, environment, preferred = null) {
    const plan = { [PlanKey.NAME]: NEW_PLAN_NAME };
    if (environment) plan[PlanKey.ENVIRONMENT] = environment;
    const state = new PlanState(catalog, plan);
    const offered = (model) => state.offeredActions({ [PlannedRobotKey.MODEL]: model[RobotModelKey.NAME] }).length;
    const models = [...catalog[PlanBuilderCatalogKey.ROBOTS]];
    models.sort((first, second) => offered(second) - offered(first));
    const chosen = models.find((model) => model[RobotModelKey.NAME] === preferred) ?? models[0];
    if (chosen) state.addRobot(chosen[RobotModelKey.NAME]);
    return state;
  }

  /**
   * @returns {Object} The catalog the plan is composed from.
   */
  get catalog() {
    return this.#catalog;
  }

  /**
   * @returns {Object} A copy of the plan document, naming the edited robot as the one
   *   that performs.
   */
  get document() {
    const plan = structuredClone(this.#plan);
    if (this.#activeRobot !== null) plan[PlanKey.SELECTED_ROBOT] = this.#activeRobot;
    return plan;
  }

  /**
   * @returns {Object} The limits plans stay within.
   */
  get limits() {
    return this.#catalog[PlanBuilderCatalogKey.LIMITS] ?? {};
  }

  // %% plan

  /**
   * @param {string} key A `PlanKey` value: the name, the task or the environment.
   * @param {string|null} value Its new value; null or empty leaves it out.
   */
  setField(key, value) {
    if (value === null || value === '') delete this.#plan[key];
    else this.#plan[key] = value;
  }

  /**
   * @param {string} key A `PlanKey` value.
   * @returns {string} Its value, or the empty text.
   */
  field(key) {
    return this.#plan[key] ?? '';
  }

  // %% actions

  /**
   * @returns {Array<Object>} Every action schema of the catalog, available or not.
   */
  actions() {
    return this.#catalog[PlanBuilderCatalogKey.ACTIONS] ?? [];
  }

  /**
   * @param {string} name An action's class name.
   * @returns {Object|null} Its schema, or null when the catalog has none.
   */
  schema(name) {
    return this.actions().find((schema) => schema[ActionSchemaKey.NAME] === name) ?? null;
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @param {Object} field An enumeration field of an action schema.
   * @returns {Array<string>} The members the robot's model offers for it: its own
   *   choices of the enumeration, else every member.
   */
  choices(robot, field) {
    const choices = this.model(robot[PlannedRobotKey.MODEL])[RobotModelKey.CHOICES] ?? {};
    return choices[field[ActionFieldKey.ENUM_TYPE]] ?? field[ActionFieldKey.MEMBERS] ?? [];
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @param {Object} schema An action schema.
   * @returns {string|null} Why the robot cannot take the action, or null when it can:
   *   the action is available and every required enumeration offers a member.
   */
  refusal(robot, schema) {
    if (!schema[ActionSchemaKey.AVAILABLE]) return schema[ActionSchemaKey.UNAVAILABLE_REASON] ?? 'unavailable';
    const lacking = PlanState.fields(schema).find((field) => field[ActionFieldKey.REQUIRED] && field[ActionFieldKey.KIND] === ActionFieldKind.ENUM && this.choices(robot, field).length === 0);
    return lacking ? `${this.modelLabel(robot[PlannedRobotKey.MODEL])} offers no ${lacking[ActionFieldKey.ENUM_TYPE]} for field '${lacking[ActionFieldKey.NAME]}'` : null;
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @returns {Array<Object>} The schemas of the actions the robot can take, in the
   *   catalog's order.
   */
  offeredActions(robot) {
    return this.actions().filter((schema) => this.refusal(robot, schema) === null);
  }

  /**
   * @param {Object} schema An action schema.
   * @returns {Array<Object>} Its fields, required ones first.
   */
  static fields(schema) {
    return schema[ActionSchemaKey.FIELDS] ?? [];
  }

  // %% robots

  /**
   * @returns {Array<Object>} The robots, in the order they were added.
   */
  robots() {
    return this.#plan[PlanKey.ROBOTS];
  }

  /**
   * @param {string} identifier A robot's identity.
   * @returns {Object} The robot.
   * @throws {PlanRefused} When the plan has no such robot.
   */
  robot(identifier) {
    const robot = this.robots().find((candidate) => candidate[PlannedRobotKey.IDENTIFIER] === identifier);
    if (!robot) throw new PlanRefused(`The plan has no robot ${identifier}.`);
    return robot;
  }

  /**
   * @returns {Object|null} The robot whose steps are edited.
   */
  activeRobot() {
    return this.#activeRobot === null ? null : this.robot(this.#activeRobot);
  }

  /**
   * @param {string} identifier The robot whose steps to edit.
   */
  selectRobot(identifier) {
    this.robot(identifier);
    this.#activeRobot = identifier;
  }

  /**
   * @param {string} name A robot model's identifier.
   * @returns {Object} The model as the catalog lists it.
   * @throws {PlanRefused} When the catalog has no such model.
   */
  model(name) {
    const model = this.#catalog[PlanBuilderCatalogKey.ROBOTS].find((candidate) => candidate[RobotModelKey.NAME] === name);
    if (!model) throw new PlanRefused(`The catalog has no robot ${name}.`);
    return model;
  }

  /**
   * @param {string} name A robot model's identifier.
   * @returns {string} The model's display name, its identifier in catalogs that give
   *   none.
   */
  modelLabel(name) {
    return this.model(name)[RobotModelKey.LABEL] || name;
  }

  /**
   * @param {string} modelName A robot model's identifier.
   * @returns {string} The new robot's identity; it is edited from now on.
   * @throws {PlanRefused} When the plan holds as many robots as it may.
   */
  addRobot(modelName) {
    this.model(modelName);
    this.#within(this.robots(), PlanBuilderLimitsKey.MAXIMUM_ROBOTS);
    const identifier = this.#nextIdentity(IdentityPrefix.ROBOT, this.robots().map((robot) => robot[PlannedRobotKey.IDENTIFIER]));
    const sameModel = this.robots().filter((robot) => robot[PlannedRobotKey.MODEL] === modelName).length;
    this.robots().push({
      [PlannedRobotKey.IDENTIFIER]: identifier,
      [PlannedRobotKey.MODEL]: modelName,
      [PlannedRobotKey.LABEL]: `${this.modelLabel(modelName)} ${sameModel + 1}`,
      [PlannedRobotKey.POSE]: PlanPose.of(0, this.robots().length * ROBOT_SPACING, 0, 0),
      [PlannedRobotKey.JOINT_POSITIONS]: {},
      [PlannedRobotKey.STEPS]: [],
    });
    this.#activeRobot = identifier;
    return identifier;
  }

  /**
   * Remove a robot; the plan keeps at least one.
   * @param {string} identifier The robot's identity.
   * @returns {boolean} Whether it was removed.
   */
  removeRobot(identifier) {
    if (this.robots().length <= 1) return false;
    this.robot(identifier);
    this.#plan[PlanKey.ROBOTS] = this.robots().filter((robot) => robot[PlannedRobotKey.IDENTIFIER] !== identifier);
    if (this.#activeRobot === identifier) this.#activeRobot = this.robots()[0][PlannedRobotKey.IDENTIFIER];
    return true;
  }

  /**
   * Change a robot's model, keeping the steps whose actions the new model can take and
   * moving their enumeration values to members it offers; its posture belongs to the
   * old model and is dropped, and a name made from the old model's name takes the new
   * one's.
   * @param {string} identifier The robot's identity.
   * @param {string} modelName The new model's identifier.
   * @returns {number} How many steps were dropped.
   */
  setRobotModel(identifier, modelName) {
    const robot = this.robot(identifier);
    this.model(modelName);
    const previous = this.modelLabel(robot[PlannedRobotKey.MODEL]);
    const next = this.modelLabel(modelName);
    if (robot[PlannedRobotKey.LABEL].startsWith(`${previous} `)) robot[PlannedRobotKey.LABEL] = `${next}${robot[PlannedRobotKey.LABEL].slice(previous.length)}`;
    robot[PlannedRobotKey.MODEL] = modelName;
    robot[PlannedRobotKey.JOINT_POSITIONS] = {};
    const offered = new Set(this.offeredActions(robot).map((schema) => schema[ActionSchemaKey.NAME]));
    const kept = robot[PlannedRobotKey.STEPS].filter((step) => offered.has(step[PlanStepKey.ACTION]));
    for (const step of kept) {
      const values = step[PlanStepKey.VALUES];
      for (const field of PlanState.fields(this.schema(step[PlanStepKey.ACTION]))) {
        const name = field[ActionFieldKey.NAME];
        if (field[ActionFieldKey.KIND] !== ActionFieldKind.ENUM || values[name] === undefined) continue;
        if (!this.choices(robot, field).includes(values[name])) values[name] = this.#defaultMember(robot, field);
      }
    }
    const dropped = robot[PlannedRobotKey.STEPS].length - kept.length;
    robot[PlannedRobotKey.STEPS] = kept;
    return dropped;
  }

  /**
   * @param {string} identifier The robot's identity.
   * @param {string} label Its new display name; a blank one keeps the old.
   */
  setRobotLabel(identifier, label) {
    if (label.trim()) this.robot(identifier)[PlannedRobotKey.LABEL] = label.trim();
  }

  /**
   * @param {string} identifier The robot's identity.
   * @param {Array<number>} pose Where it starts.
   */
  setRobotPose(identifier, pose) {
    this.robot(identifier)[PlannedRobotKey.POSE] = pose;
  }

  /**
   * @param {string} identifier The robot's identity.
   * @param {Object<string, number>} positions Its start posture by joint name.
   */
  setRobotPosture(identifier, positions) {
    this.robot(identifier)[PlannedRobotKey.JOINT_POSITIONS] = { ...positions };
  }

  // %% steps

  /**
   * @returns {Array<Object>} The edited robot's steps, in the order they run.
   */
  steps() {
    return this.activeRobot()?.[PlannedRobotKey.STEPS] ?? [];
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @returns {Object} The step.
   * @throws {PlanRefused} When the robot has no such step.
   */
  step(identifier) {
    const step = this.steps().find((candidate) => candidate[PlanStepKey.IDENTIFIER] === identifier);
    if (!step) throw new PlanRefused(`The robot has no step ${identifier}.`);
    return step;
  }

  /**
   * Add a step to the edited robot with the values it can run with right away: the
   * first object, the robot's first choice or the field's default, a target ahead of
   * the robot or beside the object it puts down.
   * @param {string} action The class name of an action the robot can take.
   * @param {number=} index Where the step goes; at the end by default.
   * @returns {string} The step's identity.
   * @throws {PlanRefused} When the robot cannot take the action or the plan is full.
   */
  addStep(action, index = this.steps().length) {
    const robot = this.activeRobot();
    const schema = this.schema(action);
    const refusal = robot && schema ? this.refusal(robot, schema) : `the catalog has no action ${action}`;
    if (refusal !== null) throw new PlanRefused(`The robot cannot take ${action}: ${refusal}.`);
    this.#within(this.steps(), PlanBuilderLimitsKey.MAXIMUM_STEPS);
    const identifier = this.#nextIdentity(IdentityPrefix.STEP, this.steps().map((step) => step[PlanStepKey.IDENTIFIER]));
    const step = { [PlanStepKey.IDENTIFIER]: identifier, [PlanStepKey.ACTION]: action, [PlanStepKey.VALUES]: {}, [PlanStepKey.CONSTRAINTS]: [] };
    const values = step[PlanStepKey.VALUES];
    for (const field of PlanState.fields(schema)) {
      if (field[ActionFieldKey.REQUIRED] && field[ActionFieldKey.KIND] === ActionFieldKind.BODY && this.objects().length > 0) values[field[ActionFieldKey.NAME]] = this.objects()[0][PlannedObjectKey.IDENTIFIER];
    }
    for (const field of PlanState.fields(schema)) {
      if (!field[ActionFieldKey.REQUIRED]) continue;
      const value = this.#defaultValue(robot, schema, field, step);
      if (value !== undefined) values[field[ActionFieldKey.NAME]] = value;
    }
    this.steps().splice(index, 0, step);
    return identifier;
  }

  /**
   * @param {string} identifier A step of the edited robot.
   */
  removeStep(identifier) {
    this.step(identifier);
    const robot = this.activeRobot();
    robot[PlannedRobotKey.STEPS] = this.steps().filter((step) => step[PlanStepKey.IDENTIFIER] !== identifier);
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {number} offset How many places it moves, negative for earlier.
   */
  moveStep(identifier, offset) {
    const steps = this.steps();
    const from = steps.indexOf(this.step(identifier));
    const to = from + offset;
    if (to < 0 || to >= steps.length) return;
    const [step] = steps.splice(from, 1);
    steps.splice(to, 0, step);
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {string} name The name of a field of the step's action.
   * @param {*} value Its JSON value; null leaves the field to the action's default.
   */
  setValue(identifier, name, value) {
    const values = this.step(identifier)[PlanStepKey.VALUES];
    if (value === null) delete values[name];
    else values[name] = value;
  }

  /**
   * Choose whether a field accepting a surface names a pose or a surface; a pose starts
   * beside the step's object, a surface as the catalog's first surface type.
   * @param {string} identifier A step of the edited robot.
   * @param {string} name The name of a field accepting a surface.
   * @param {string} placement A `PlacementMode` value.
   */
  setPlacement(identifier, name, placement) {
    const step = this.step(identifier);
    const destination = { ...(step[PlanStepKey.VALUES][name] ?? {}), [DestinationKey.PLACEMENT]: placement };
    if (placement === PlacementMode.POSE) destination[DestinationKey.POSE] ??= this.#besideObject(step);
    if (placement === PlacementMode.SURFACE) destination[DestinationKey.SURFACE_TYPE] ??= this.#catalog[PlanBuilderCatalogKey.SURFACE_TYPES][0];
    step[PlanStepKey.VALUES][name] = destination;
  }

  /**
   * @param {Object} step A step of the plan.
   * @returns {string|undefined} The identity of the object it acts on: the value of
   *   its action's first body field.
   */
  stepObject(step) {
    const body = PlanState.fields(this.schema(step[PlanStepKey.ACTION]) ?? {}).find((field) => field[ActionFieldKey.KIND] === ActionFieldKind.BODY);
    return body ? step[PlanStepKey.VALUES][body[ActionFieldKey.NAME]] : undefined;
  }

  /**
   * @param {Object} step A step of the plan.
   * @returns {Array<{field: string, pose: Array<number>, object: string|undefined}>}
   *   The poses the step names: each pose field's pose, and each destination at a pose
   *   with the object put down there.
   */
  targets(step) {
    const targets = [];
    for (const field of PlanState.fields(this.schema(step[PlanStepKey.ACTION]) ?? {})) {
      const name = field[ActionFieldKey.NAME];
      const value = step[PlanStepKey.VALUES][name];
      if (!POSE_KINDS.includes(field[ActionFieldKey.KIND]) || value === undefined) continue;
      if (!field[ActionFieldKey.ACCEPTS_SURFACE]) targets.push({ field: name, pose: value, object: undefined });
      else if (value[DestinationKey.PLACEMENT] !== PlacementMode.SURFACE && value[DestinationKey.POSE]) targets.push({ field: name, pose: value[DestinationKey.POSE], object: this.stepObject(step) });
    }
    return targets;
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {string} name A pose field, or a field accepting a surface.
   * @param {Array<number>} pose The field's new pose.
   */
  setTarget(identifier, name, pose) {
    const step = this.step(identifier);
    const field = PlanState.fields(this.schema(step[PlanStepKey.ACTION])).find((candidate) => candidate[ActionFieldKey.NAME] === name);
    if (field?.[ActionFieldKey.ACCEPTS_SURFACE]) step[PlanStepKey.VALUES][name] = { [DestinationKey.PLACEMENT]: PlacementMode.POSE, [DestinationKey.POSE]: pose };
    else step[PlanStepKey.VALUES][name] = pose;
  }

  /**
   * @param {Object} step A step of the edited robot.
   * @returns {Array<string>} What keeps the step from running as it stands, checked
   *   against its action's schema and the robot's choices: the server refuses such a
   *   step when a demo is written or run.
   */
  problems(step) {
    const schema = this.schema(step[PlanStepKey.ACTION]);
    if (!schema) return [`The installed CRAM offers no action ${step[PlanStepKey.ACTION]}.`];
    const robot = this.activeRobot();
    const refusal = this.refusal(robot, schema);
    if (refusal !== null) return [`${schema[ActionSchemaKey.LABEL]} is not available: ${refusal}.`];
    const problems = [];
    const values = step[PlanStepKey.VALUES];
    const fields = new Map(PlanState.fields(schema).map((field) => [field[ActionFieldKey.NAME], field]));
    for (const [name, value] of Object.entries(values)) {
      const field = fields.get(name);
      if (!field) problems.push(`${schema[ActionSchemaKey.LABEL]} has no field '${name}'.`);
      else if (!this.#fits(robot, field, value)) problems.push(`Field '${name}' cannot be ${JSON.stringify(value)}.`);
    }
    for (const field of fields.values()) {
      if (field[ActionFieldKey.REQUIRED] && field[ActionFieldKey.KIND] !== ActionFieldKind.GRASP && values[field[ActionFieldKey.NAME]] === undefined) problems.push(`Field '${field[ActionFieldKey.NAME]}' needs a value.`);
    }
    return problems;
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {Object} constraint A compiled `StepConstraint`.
   * @returns {boolean} Whether it was attached; a step holds each sentence once.
   * @throws {PlanRefused} When the step holds as many constraints as it may.
   */
  attachConstraint(identifier, constraint) {
    const constraints = this.step(identifier)[PlanStepKey.CONSTRAINTS];
    if (constraints.some((attached) => attached[StepConstraintKey.TEXT] === constraint[StepConstraintKey.TEXT])) return false;
    this.#within(constraints, PlanBuilderLimitsKey.MAXIMUM_CONSTRAINTS);
    constraints.push(constraint);
    return true;
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {number} index The position of the constraint to remove.
   */
  detachConstraint(identifier, index) {
    this.step(identifier)[PlanStepKey.CONSTRAINTS].splice(index, 1);
  }

  // %% objects

  /**
   * @returns {Array<Object>} The free objects, in the order they were added.
   */
  objects() {
    return this.#plan[PlanKey.OBJECTS];
  }

  /**
   * @param {string} identifier An object's identity.
   * @returns {Object} The object.
   * @throws {PlanRefused} When the plan has no such object.
   */
  object(identifier) {
    const found = this.objects().find((candidate) => candidate[PlannedObjectKey.IDENTIFIER] === identifier);
    if (!found) throw new PlanRefused(`The plan has no object ${identifier}.`);
    return found;
  }

  /**
   * Add a copy of an object model in front of the edited robot, spread out from the
   * objects added before.
   * @param {string} modelIdentifier The identifier of an object model.
   * @returns {string} The object's identity, made from the model's name.
   * @throws {PlanRefused} When the catalog has no such model or the plan is full.
   */
  addObject(modelIdentifier) {
    const model = this.#catalog[PlanBuilderCatalogKey.OBJECTS].find((candidate) => candidate[ObjectModelKey.IDENTIFIER] === modelIdentifier);
    if (!model) throw new PlanRefused(`The catalog has no object ${modelIdentifier}.`);
    this.#within(this.objects(), PlanBuilderLimitsKey.MAXIMUM_OBJECTS);
    const base = model[ObjectModelKey.NAME].replace(NON_IDENTITY_CHARACTERS, '_');
    const name = IDENTITY_START.test(base) ? base : `${IdentityPrefix.OBJECT}${base}`;
    const taken = this.objects().map((item) => item[PlannedObjectKey.IDENTIFIER]);
    const identifier = taken.includes(name) ? this.#nextIdentity(`${name}_`, taken) : name;
    const robotPose = this.activeRobot()?.[PlannedRobotKey.POSE] ?? PlanPose.of(0, 0, 0, 0);
    const [x, y] = PlanPose.position(robotPose);
    const yaw = PlanPose.yaw(robotPose);
    const sideways = (this.objects().length % 2 === 0 ? 1 : -1) * Math.ceil(this.objects().length / 2) * Placement.OBJECT_SPREAD;
    this.objects().push({
      [PlannedObjectKey.IDENTIFIER]: identifier,
      [PlannedObjectKey.MODEL]: modelIdentifier,
      [PlannedObjectKey.POSE]: PlanPose.of(
        PlanPose.rounded(x + Placement.OBJECT_AHEAD * Math.cos(yaw) - sideways * Math.sin(yaw)),
        PlanPose.rounded(y + Placement.OBJECT_AHEAD * Math.sin(yaw) + sideways * Math.cos(yaw)),
        Placement.OBJECT_HEIGHT,
        0,
      ),
    });
    return identifier;
  }

  /**
   * Remove an object; steps acting on it act on the first remaining object, or on none.
   * @param {string} identifier The object's identity.
   */
  removeObject(identifier) {
    this.object(identifier);
    this.#plan[PlanKey.OBJECTS] = this.objects().filter((item) => item[PlannedObjectKey.IDENTIFIER] !== identifier);
    const replacement = this.objects()[0]?.[PlannedObjectKey.IDENTIFIER];
    for (const robot of this.robots()) {
      for (const step of robot[PlannedRobotKey.STEPS]) {
        const values = step[PlanStepKey.VALUES];
        for (const field of PlanState.fields(this.schema(step[PlanStepKey.ACTION]) ?? {})) {
          const name = field[ActionFieldKey.NAME];
          if (field[ActionFieldKey.KIND] !== ActionFieldKind.BODY || values[name] !== identifier) continue;
          if (replacement === undefined) delete values[name];
          else values[name] = replacement;
        }
      }
    }
  }

  /**
   * @param {string} identifier The object's identity.
   * @param {Array<number>} pose Where it starts.
   */
  setObjectPose(identifier, pose) {
    this.object(identifier)[PlannedObjectKey.POSE] = pose;
  }

  /**
   * @param {string} identifier The object's identity.
   * @param {string|null} color A CSS hexadecimal colour, or null for the model's own.
   */
  setObjectColor(identifier, color) {
    const found = this.object(identifier);
    if (color === null) delete found[PlannedObjectKey.COLOR];
    else found[PlannedObjectKey.COLOR] = color;
  }

  // %% defaults

  /**
   * @param {Object} robot The robot taking the step.
   * @param {Object} schema The step's action.
   * @param {Object} field A required field of it.
   * @param {Object} step The step being added, with its objects chosen.
   * @returns {*} The field's starting value, or undefined to leave it for the person.
   */
  #defaultValue(robot, schema, field, step) {
    const kind = field[ActionFieldKey.KIND];
    if (kind === ActionFieldKind.ENUM) return this.#defaultMember(robot, field);
    if (POSE_KINDS.includes(kind) && field[ActionFieldKey.ACCEPTS_SURFACE]) return { [DestinationKey.PLACEMENT]: PlacementMode.POSE, [DestinationKey.POSE]: this.#besideObject(step) };
    if (kind === ActionFieldKind.POSE) return this.#nextTarget(robot, schema, field);
    if (kind in PLAIN_TYPES && kind !== ActionFieldKind.ANNOTATION) return field[ActionFieldKey.DEFAULT] ?? undefined;
    return undefined;
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @param {Object} field An enumeration field.
   * @returns {string|undefined} The field's default when the robot offers it, else the
   *   robot's first choice.
   */
  #defaultMember(robot, field) {
    const choices = this.choices(robot, field);
    return choices.includes(field[ActionFieldKey.DEFAULT]) ? field[ActionFieldKey.DEFAULT] : choices[0];
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @param {Object} schema An action.
   * @param {Object} field One of its pose fields.
   * @returns {Array<number>} A little beyond the same field's pose in the robot's last
   *   step of the action, or ahead of the robot on the floor.
   */
  #nextTarget(robot, schema, field) {
    const name = field[ActionFieldKey.NAME];
    const previous = robot[PlannedRobotKey.STEPS].filter((step) => step[PlanStepKey.ACTION] === schema[ActionSchemaKey.NAME] && PlanPose.isPose(step[PlanStepKey.VALUES][name])).pop();
    if (previous) {
      const pose = previous[PlanStepKey.VALUES][name];
      const [x, y, z] = PlanPose.position(pose);
      return PlanPose.moved(pose, [x + Placement.NEXT_TARGET_STEP, y, z]);
    }
    const pose = robot[PlannedRobotKey.POSE];
    const [x, y] = PlanPose.position(pose);
    const yaw = PlanPose.yaw(pose);
    return PlanPose.of(PlanPose.rounded(x + Placement.TARGET_AHEAD * Math.cos(yaw)), PlanPose.rounded(y + Placement.TARGET_AHEAD * Math.sin(yaw)), 0, yaw);
  }

  /**
   * @param {Object} step A step that puts an object down.
   * @returns {Array<number>|undefined} A pose beside where the step's object starts,
   *   or undefined without an object.
   */
  #besideObject(step) {
    const placed = this.objects().find((item) => item[PlannedObjectKey.IDENTIFIER] === this.stepObject(step));
    if (!placed) return undefined;
    const [x, y, z] = PlanPose.position(placed[PlannedObjectKey.POSE]);
    return PlanPose.moved(placed[PlannedObjectKey.POSE], [x, y + Placement.PUT_DOWN_BESIDE, z]);
  }

  /**
   * @param {Object} robot The robot taking the step.
   * @param {Object} field A field of the step's action.
   * @param {*} value A value of the step.
   * @returns {boolean} Whether the value fits the field's kind and the robot's choices.
   */
  #fits(robot, field, value) {
    const kind = field[ActionFieldKey.KIND];
    if (kind === ActionFieldKind.GRASP) return false;
    if (kind === ActionFieldKind.BODY) return this.objects().some((item) => item[PlannedObjectKey.IDENTIFIER] === value);
    if (kind === ActionFieldKind.ENUM) return this.choices(robot, field).includes(value);
    if (kind === ActionFieldKind.INTEGER) return Number.isInteger(value);
    if (kind in PLAIN_TYPES) return typeof value === PLAIN_TYPES[kind];
    if (!field[ActionFieldKey.ACCEPTS_SURFACE]) return PlanPose.isPose(value);
    if (value?.[DestinationKey.PLACEMENT] === PlacementMode.SURFACE) return typeof value[DestinationKey.SURFACE_TYPE] === 'string';
    return PlanPose.isPose(value?.[DestinationKey.POSE]);
  }

  /**
   * @param {string} prefix The identity's prefix.
   * @param {Array<string>} taken The identities in use.
   * @returns {string} The prefix with the smallest number not in use.
   */
  #nextIdentity(prefix, taken) {
    let number = 1;
    while (taken.includes(`${prefix}${number}`)) number += 1;
    return `${prefix}${number}`;
  }

  /**
   * @param {Array} entries A list of the plan.
   * @param {string} limit The `PlanBuilderLimitsKey` bounding it.
   * @throws {PlanRefused} When the list holds as many entries as the limit allows.
   */
  #within(entries, limit) {
    const maximum = this.limits[limit];
    if (maximum !== undefined && entries.length >= maximum) throw new PlanRefused(`At most ${maximum} fit.`);
  }
}
